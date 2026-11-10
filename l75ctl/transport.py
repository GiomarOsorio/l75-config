"""Transportes: HID real (hidapi), simulado (demo) y "dry-run" (solo mostrar)."""

from __future__ import annotations

import sys
import threading
import time
from dataclasses import dataclass

from . import protocol as P
from .i18n import t


class TransportError(RuntimeError):
    pass


class DeviceNotFound(TransportError):
    pass


class PermissionDenied(TransportError):
    """The device exists but cannot be opened (udev rule missing on Linux, or in use)."""


class NoResponse(TransportError):
    """The keyboard did not answer in time."""


class Cancelled(TransportError):
    """The user cancelled a long operation (screen upload)."""


@dataclass
class DeviceInfo:
    path: bytes
    bus: str
    vid: int
    pid: int
    interface: int
    usage_page: int
    usage: int
    product: str
    manufacturer: str


class Transport:
    """Interfaz comun. Paquetes de 64 bytes SIN el report ID."""

    name = "base"
    bus = "usb"

    def write(self, buf: bytes) -> None:
        raise NotImplementedError

    def read(self) -> bytes:
        raise NotImplementedError

    def close(self) -> None:
        pass


def _hid_module():
    # En Linux, el paquete `hidapi` de pip trae dos módulos: `hid` (libusb, no ve el Bluetooth)
    # y `hidraw` (el bueno). Si está, se usa `hidraw`; si no, `hid` (python3-hid / pyhidapi).
    if sys.platform.startswith("linux"):
        try:
            import hidraw  # type: ignore

            return hidraw
        except ImportError:
            pass
    try:
        import hid  # type: ignore
    except ImportError as exc:  # pragma: no cover - depende del sistema
        raise TransportError(
            t("The 'hid' module is missing. Install hidapi for Python:") + "\n"
            "  sudo dnf install python3-hid hidapi    (Fedora/Nobara)\n"
            "  " + t("or:") + " pip install --user hidapi"
        ) from exc
    return hid


def list_devices(include_dongles: bool = False) -> list[DeviceInfo]:
    """Interfaces de configuracion del L75: por cable (bus "usb") y Bluetooth ("bt")."""
    hid = _hid_module()
    found: list[DeviceInfo] = []
    seen: set[bytes] = set()
    for d in hid.enumerate(P.VID, 0):
        pid = d.get("product_id")
        usage_page = d.get("usage_page", 0)
        iface = d.get("interface_number", -1)
        bus = None
        if pid == P.PID_WIRED or (include_dongles and pid in P.PID_DONGLES):
            # En Linux (hidraw) usage_page suele venir bien; si no, usar interfaz 2.
            if usage_page == P.USAGE_PAGE or (usage_page == 0 and iface == P.INTERFACE):
                bus = "usb" if pid == P.PID_WIRED else "dongle"
        elif pid in P.PID_BLUETOOTH:
            if usage_page in P.BLE_USAGE_PAGES:
                bus = "bt"
        if bus is None or d["path"] in seen:
            continue
        seen.add(d["path"])
        found.append(DeviceInfo(
            path=d["path"], bus=bus, vid=d["vendor_id"], pid=pid,
            interface=iface, usage_page=usage_page, usage=d.get("usage", 0),
            product=d.get("product_string") or "", manufacturer=d.get("manufacturer_string") or "",
        ))
    return found


class _CythonHidDevice:
    """Adapta el módulo `hidapi` de pip (cython-hidapi, `hid.device()`) a la API de pyhidapi.

    Los paquetes para Windows y macOS usan `hidapi`, que ya trae la librería nativa;
    en Linux suele estar `python3-hid` (pyhidapi, `hid.Device`). Las dos se importan como `hid`.
    """

    def __init__(self, hid, path: bytes):
        self._d = hid.device()
        self._d.open_path(path)

    def send_feature_report(self, data: bytes) -> int:
        n = self._d.send_feature_report(list(data))
        if n < 0:
            raise OSError("send_feature_report fallo")
        return n

    def get_feature_report(self, report_id: int, size: int) -> bytes:
        return bytes(self._d.get_feature_report(report_id, size))

    def read(self, size: int, timeout: int = 0) -> bytes:
        # en cython-hidapi, timeout 0 bloquea hasta que llegue algo; pyhidapi devuelve al momento
        return bytes(self._d.read(size, max(1, int(timeout))))

    def write(self, data: bytes) -> int:
        n = self._d.write(list(data))
        if n < 0:
            raise OSError("write fallo")
        return n

    def close(self) -> None:
        self._d.close()


def _open_hid(path: bytes):
    hid = _hid_module()
    try:
        if hasattr(hid, "Device"):
            return hid.Device(path=path)
        return _CythonHidDevice(hid, path)
    except Exception as exc:  # hid.HIDException / OSError
        hint = (t("Probably a missing permission: install the udev rule (./install.sh) and reconnect the "
                  "keyboard (unplug the cable, or turn the keyboard's Bluetooth off and on).")
                if sys.platform.startswith("linux") else
                t("Close the official driver or other apps using the keyboard and reconnect it."))
        raise PermissionDenied(t("Could not open {path}: {error}").format(
            path=path.decode(errors="replace"), error=exc) + "\n" + hint) from exc


def open_transport(prefer: str = "auto", path: bytes | None = None) -> "Transport":
    """Abre el teclado. prefer: auto (cable si hay, si no Bluetooth) | usb | bt."""
    if path is not None:
        dev = next((d for d in list_devices() if d.path == path), None)
        if dev and dev.bus == "bt":
            return BleTransport(path)
        return HidTransport(path)
    devs = list_devices()
    usb = [d for d in devs if d.bus == "usb"]
    bt = [d for d in devs if d.bus == "bt"]
    if prefer in ("auto", "usb") and usb:
        return HidTransport(usb[0].path)
    if prefer in ("auto", "bt") and bt:
        return BleTransport(bt[0].path)
    raise DeviceNotFound(
        t("L75 not found.") + "\n"
        + t("- Cable: USB-C plugged in and the switch in wired mode (USB 3151:4015).") + "\n"
        + t("- Bluetooth: paired and connected as 'L75 BT5.0' (3151:4012).") + "\n"
        + t("Check with: l75 list")
    )


class HidTransport(Transport):
    """Feature reports via hidapi (backend hidraw en Linux)."""

    name = "hid"

    bus = "usb"

    def __init__(self, path: bytes):
        self._dev = _open_hid(path)
        self.path = path

    def write(self, buf: bytes) -> None:
        if len(buf) != P.PACKET_SIZE:
            raise ValueError(t("the packet must be 64 bytes"))
        try:
            self._dev.send_feature_report(bytes([P.REPORT_ID]) + bytes(buf))
        except Exception as exc:
            raise TransportError(t("error sending feature report: {error}").format(error=exc)) from exc

    def read(self) -> bytes:
        try:
            data = self._dev.get_feature_report(P.REPORT_ID, P.PACKET_SIZE + 1)
        except Exception as exc:
            raise TransportError(t("error reading feature report: {error}").format(error=exc)) from exc
        data = bytes(data)
        # hidraw devuelve el report ID como primer byte.
        if len(data) == P.PACKET_SIZE + 1:
            data = data[1:]
        return data.ljust(P.PACKET_SIZE, b"\0")[: P.PACKET_SIZE]

    def close(self) -> None:
        try:
            self._dev.close()
        except Exception:
            pass


class BleTransport(Transport):
    """Bluetooth (BLE/HOGP) segun el driver oficial (iot_driver, HidBLE):

    * Escritura: OUTPUT report ID 6 -> [0x06, 0x55] + 64 bytes de comando
      (BleHid::send_msg antepone 0x55; HidBLE::send_feature antepone 0x06).
    * Lectura: INPUT reports ID 6 que el teclado envia por su cuenta:
      [0x06, 0x55, comando en eco, ...] = respuesta
      [0x06, 0x66, ...]                 = evento (cambio de perfil, luz...), se ignora.
      El driver espera la respuesta hasta 3 s (300 x 10 ms).
    El checksum es el mismo que por cable, calculado sobre los 64 bytes.
    Verificado con un L75 real (firmware 0x0111) el 2026-11-10.
    """

    name = "bt"
    bus = "bt"
    TIMEOUT_S = 3.0

    def __init__(self, path: bytes):
        self._dev = _open_hid(path)
        self.path = path
        self.events: list[bytes] = []

    def _drain(self) -> None:
        for _ in range(64):
            try:
                r = self._dev.read(P.BLE_REPORT_SIZE, timeout=0)
            except Exception:
                return
            if not r:
                return
            self._note(bytes(r))

    def _note(self, r: bytes) -> bytes | None:
        """Devuelve el payload si es una respuesta valida."""
        if len(r) < 2 or r[0] != P.BLE_REPORT_ID:
            return None  # teclas, multimedia, raton...
        payload = r[1:]
        if not any(payload):
            return None
        if payload[0] == P.BLE_EVENT_MARKER:
            self.events.append(payload)
            del self.events[:-32]
            return None
        if payload[0] == P.BLE_CMD_MARKER:
            return payload[1:]
        return None

    def write(self, buf: bytes) -> None:
        if len(buf) != P.PACKET_SIZE:
            raise ValueError(t("the packet must be 64 bytes"))
        self._drain()
        data = bytes([P.BLE_REPORT_ID, P.BLE_CMD_MARKER]) + bytes(buf)
        try:
            self._dev.write(data)
        except Exception as exc:
            raise TransportError(t("error sending over Bluetooth: {error}").format(error=exc)) from exc

    def read(self) -> bytes:
        deadline = time.monotonic() + self.TIMEOUT_S
        while True:
            left = deadline - time.monotonic()
            if left <= 0:
                raise NoResponse(t("the keyboard did not answer over Bluetooth (3 s timeout)"))
            try:
                r = self._dev.read(P.BLE_REPORT_SIZE, timeout=max(1, int(left * 1000)))
            except Exception as exc:
                raise TransportError(t("error reading over Bluetooth: {error}").format(error=exc)) from exc
            if not r:
                continue
            payload = self._note(bytes(r))
            if payload is not None:
                return payload.ljust(P.PACKET_SIZE, b"\0")[: P.PACKET_SIZE]

    def close(self) -> None:
        try:
            self._dev.close()
        except Exception:
            pass


class DryRunTransport(Transport):
    """No toca hardware: imprime cada paquete. Las lecturas devuelven ceros."""

    name = "dry-run"

    def __init__(self, out=None, max_lines: int | None = None):
        self.out = out or sys.stdout
        self.sent: list[bytes] = []
        self.max_lines = max_lines

    def write(self, buf: bytes) -> None:
        self.sent.append(bytes(buf))
        if self.max_lines is None or len(self.sent) <= self.max_lines:
            print("TX " + bytes(buf).hex(" "), file=self.out)
        elif len(self.sent) == self.max_lines + 1:
            print("TX ... (mas paquetes omitidos)", file=self.out)

    def read(self) -> bytes:
        return bytes(P.PACKET_SIZE)


class SimulatedTransport(Transport):
    """Emula un L75 en memoria para probar la app sin el teclado (modo demo).

    Implementa los comandos que usa esta app con el mismo formato que el
    teclado real (segun el driver oficial). Es una aproximacion: sirve para
    probar la interfaz, no para garantizar el comportamiento del firmware.
    """

    name = "demo"

    def __init__(self):
        from .l75_data import DEFAULT_MATRIX

        flat = bytes(b for slot in DEFAULT_MATRIX for b in slot)
        self.matrix = [bytearray(flat) for _ in range(P.NUM_PROFILES)]
        from .l75_data import DEFAULT_FN_LAYER

        self.fn_matrix = [bytearray(len(flat)) for _ in range(P.NUM_FN_LAYERS)]
        for slot, raw in DEFAULT_FN_LAYER.items():
            self.fn_matrix[0][slot * 4:slot * 4 + 4] = bytes(raw)
        self.macros = [bytearray(P.MACRO_BUFFER) for _ in range(P.MACRO_MAX)]
        self.userpic = bytearray(P.MATRIX_SLOTS * 3)
        self.profile = 0
        self.kbopt = [0, 0, 0]
        self.report_code = 1
        self.debounce = 5
        self.sleep = [120, 120, 1680, 1680]
        self.led = bytearray([P.Cmd.SET_LEDPARAM, 4, 2, 4, 8, 255, 255, 255])
        self.sled = bytearray([P.Cmd.SET_SLEDPARAM, 1, 2, 4, 8, 255, 255, 255])
        self.lcd_frames_received = 0
        self.log: list[bytes] = []
        self._resp = bytes(P.PACKET_SIZE)
        self._lock = threading.Lock()

    # -- helpers
    def _reply(self, *data: int, raw: bytes | None = None) -> None:
        if raw is not None:
            self._resp = bytes(raw).ljust(P.PACKET_SIZE, b"\0")[: P.PACKET_SIZE]
        else:
            self._resp = bytes(data).ljust(P.PACKET_SIZE, b"\0")

    def write(self, buf: bytes) -> None:
        with self._lock:
            self._handle(bytes(buf))

    def _handle(self, b: bytes) -> None:
        self.log.append(b)
        c = b[0]
        C = P.Cmd
        if c == C.GET_REV:
            self._reply(c, 0x05, 0x01)
        elif c == C.GET_INFOR:
            self._reply(c, *P.u16le(P.DEVICE_ID_L75))
        elif c == C.GET_BATTERY:
            self._reply(c, 87, 0)
        elif c == C.SET_PROFILE:
            self.profile = b[1] % P.NUM_PROFILES
        elif c == C.GET_PROFILE:
            self._reply(c, self.profile)
        elif c == C.SET_REPORT:
            self.report_code = b[2]
        elif c == C.GET_REPORT:
            self._reply(c, b[1], self.report_code)
        elif c == C.SET_KBOPTION:
            self.kbopt = [b[2], b[3], b[4]]
        elif c == C.GET_KBOPTION:
            self._reply(c, b[1], *self.kbopt)
        elif c == C.SET_DEBOUNCE:
            self.debounce = b[2]
        elif c == C.GET_DEBOUNCE:
            self._reply(c, 0, self.debounce)
        elif c == C.SET_SLEEPTIME:
            self.sleep = [b[8] | b[9] << 8, b[10] | b[11] << 8, b[12] | b[13] << 8, b[14] | b[15] << 8]
        elif c == C.GET_SLEEPTIME:
            out = [c]
            for v in self.sleep:
                out += list(P.u16le(v))
            self._reply(*out)
        elif c == C.SET_LEDPARAM:
            self.led = bytearray(b[:8])
        elif c == C.GET_LEDPARAM:
            self._reply(raw=bytes([c]) + bytes(self.led[1:8]))
        elif c == C.SET_SLEDPARAM:
            self.sled = bytearray(b[:8])
        elif c == C.GET_SLEDPARAM:
            self._reply(raw=bytes([c]) + bytes(self.sled[1:8]))
        elif c == C.GET_KEYMATRIX:
            prof, page = b[1] % P.NUM_PROFILES, b[2]
            self._reply(raw=self.matrix[prof][page * 64:(page + 1) * 64])
        elif c == C.GET_FN_KEYMATRIX:
            layer, page = b[1] % P.NUM_FN_LAYERS, b[2]
            self._reply(raw=self.fn_matrix[layer][page * 64:(page + 1) * 64])
        elif c == C.SET_KEYMATRIX_SIMPLE:
            prof, slot = b[1] % P.NUM_PROFILES, b[2]
            self.matrix[prof][slot * 4:slot * 4 + 4] = b[8:12]
        elif c == C.SET_FN_SIMPLE:
            layer, slot = b[1] % P.NUM_FN_LAYERS, b[2]
            self.fn_matrix[layer][slot * 4:slot * 4 + 4] = b[8:12]
        elif c == C.SET_MACRO_SIMPLE:
            idx, page, length = b[1], b[2], b[3]
            if idx < P.MACRO_MAX:
                buf = self.macros[idx]
                if page == 0:
                    buf[:] = bytes(P.MACRO_BUFFER)
                start = page * 56
                chunk = b[8:8 + length][: max(0, P.MACRO_BUFFER - start)]
                buf[start:start + len(chunk)] = chunk
        elif c == C.GET_MACRO:
            idx, page = b[1], b[2]
            data = self.macros[idx] if idx < P.MACRO_MAX else bytes(P.MACRO_BUFFER)
            self._reply(raw=data[page * 64:(page + 1) * 64])
        elif c == C.SET_USERPIC_SIMPLE:
            slot = b[2]
            self.userpic[slot * 3:slot * 3 + 3] = b[8:11]
        elif c == C.GET_USERPIC:
            page = b[2]
            self._reply(raw=self.userpic[page * 64:(page + 1) * 64])
        elif c == C.SET_RESET:
            self.__init__()
        elif c == C.GET_TFTLCD_DATA:
            self._reply(c, 1)
        elif c == C.SET_TFTLCD_DATA:
            if b[4] == 0 and b[5] == 0:
                self.lcd_frames_received += 1
        # resto: aceptar en silencio

    def read(self) -> bytes:
        with self._lock:
            return self._resp


def sleep_ms(ms: float) -> None:
    if ms > 0:
        time.sleep(ms / 1000.0)
