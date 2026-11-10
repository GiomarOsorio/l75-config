"""API de alto nivel para el ROYALAXE / ProtoArc L75."""

from __future__ import annotations

import datetime as _dt
import threading
from dataclasses import dataclass
from typing import Callable

from . import lcd
from . import lighting as L
from . import protocol as P
from .keymap import Action, PhysicalKey, matrix_to_actions
from .macros import Macro, decode_macro, encode_macro, macro_pages
from .transport import (DryRunTransport, SimulatedTransport, Transport, TransportError, open_transport,
                        sleep_ms)

Progress = Callable[[float, str], None]


@dataclass
class KeyboardOptions:
    win_lock: bool = False
    mac_mode: bool = False
    wasd_arrows_swap: bool = False
    led_off: bool = False
    side_led_off: bool = False
    keyboard_mode: bool = False
    keyboard_lock: bool = False
    fn_matrix: bool = False
    power_save: bool = False
    raw: tuple[int, int, int] = (0, 0, 0)


@dataclass
class SleepTimes:
    """Segundos hasta reposo (0 = nunca) y reposo profundo, en BT y 2.4G."""
    bt: int = 120
    rf24: int = 120
    deep_bt: int = 1680
    deep_rf24: int = 1680


class L75:
    """Conexion con el teclado. Seguro para usar desde varios hilos."""

    WRITE_DELAY_MS = 10
    READ_DELAY_MS = 5

    def __init__(self, transport: Transport):
        self.t = transport
        self._lock = threading.RLock()
        self.profile = 0
        if transport.bus == "bt":
            # el driver oficial espera 60 ms extra antes de cada envio por Bluetooth
            self.WRITE_DELAY_MS = 70
            self.READ_DELAY_MS = 0

    # ------------------------------------------------------------ apertura
    @classmethod
    def open(cls, demo: bool = False, dry_run: bool = False, path: bytes | None = None,
             prefer: str = "auto") -> "L75":
        """prefer: auto (cable si esta conectado, si no Bluetooth) | usb | bt."""
        if demo:
            return cls(SimulatedTransport())
        if dry_run:
            return cls(DryRunTransport())
        return cls(open_transport(prefer, path))

    @property
    def bus(self) -> str:
        """'usb' (cable) o 'bt' (Bluetooth)."""
        return self.t.bus

    @property
    def is_demo(self) -> bool:
        return isinstance(self.t, SimulatedTransport)

    @property
    def is_dry_run(self) -> bool:
        return isinstance(self.t, DryRunTransport)

    def close(self) -> None:
        self.t.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # ------------------------------------------------------------ bajo nivel
    def send(self, buf: bytes | bytearray, checksum: P.Checksum | None = P.Checksum.BIT7,
             delay_ms: float | None = None) -> None:
        b = bytearray(buf)
        if len(b) != P.PACKET_SIZE:
            b = b.ljust(P.PACKET_SIZE, b"\0")[: P.PACKET_SIZE]
        if b[0] in P.FORBIDDEN_CMDS:
            raise ValueError(f"comando 0x{b[0]:02X} bloqueado (firmware/bootloader)")
        if checksum is not None:
            P.apply_checksum(b, checksum)
        with self._lock:
            sleep_ms(self.WRITE_DELAY_MS if delay_ms is None else delay_ms)
            self.t.write(bytes(b))

    def query(self, buf: bytes | bytearray, checksum: P.Checksum = P.Checksum.BIT7,
              read_delay_ms: float | None = None) -> bytes:
        with self._lock:
            self.send(buf, checksum)
            sleep_ms(self.READ_DELAY_MS if read_delay_ms is None else read_delay_ms)
            return self.t.read()

    def _get(self, cmd: int, *args: int) -> bytes:
        return self.query(P.packet(cmd, *args))

    # ------------------------------------------------------------ info
    def firmware_version(self) -> int:
        r = self._get(P.Cmd.GET_REV)
        return r[1] | r[2] << 8

    def device_info_raw(self) -> bytes:
        return self._get(P.Cmd.GET_INFOR)

    def device_id(self) -> int:
        """ID de modelo (820 o 1007 para el L75)."""
        r = self.device_info_raw()
        return r[1] | r[2] << 8

    def battery(self) -> tuple[int, str]:
        r = self._get(P.Cmd.GET_BATTERY)
        status = {0: "descargando", 1: "cargando", 2: "cargado"}.get(r[2], f"?{r[2]}")
        return r[1], status

    # ------------------------------------------------------------ perfiles
    def get_profile(self) -> int:
        r = self._get(P.Cmd.GET_PROFILE)
        if r[1] < P.NUM_PROFILES:
            self.profile = r[1]
        return r[1]

    def set_profile(self, profile: int) -> None:
        if not 0 <= profile < P.NUM_PROFILES:
            raise ValueError("perfil 0..2")
        self.send(P.packet(P.Cmd.SET_PROFILE, profile))
        self.profile = profile
        sleep_ms(200)

    # ------------------------------------------------------------ ajustes
    def get_report_rate(self) -> int | None:
        r = self._get(P.Cmd.GET_REPORT, self.profile)
        return P.REPORT_RATE_FROM_CODE.get(r[2])

    def set_report_rate(self, hz: int) -> None:
        if hz not in P.REPORT_RATE_CODES:
            raise ValueError("tasa valida: 125, 250, 500 o 1000 Hz")
        self.send(P.packet(P.Cmd.SET_REPORT, self.profile, P.REPORT_RATE_CODES[hz]))
        sleep_ms(1000)

    def get_debounce(self) -> int:
        return self._get(P.Cmd.GET_DEBOUNCE)[2]

    def set_debounce(self, ms: int) -> None:
        if not 0 <= ms <= 50:
            raise ValueError("debounce 0..50 ms")
        self.send(P.packet(P.Cmd.SET_DEBOUNCE, 0, ms))
        sleep_ms(500)

    def get_sleep(self) -> SleepTimes:
        r = self._get(P.Cmd.GET_SLEEPTIME)
        return SleepTimes(r[1] | r[2] << 8, r[3] | r[4] << 8, r[5] | r[6] << 8, r[7] | r[8] << 8)

    def set_sleep(self, s: SleepTimes) -> None:
        vals = []
        for v in (s.bt, s.rf24, s.deep_bt, s.deep_rf24):
            if not 0 <= v <= 0xFFFF:
                raise ValueError("tiempo fuera de rango (0..65535 s)")
            vals += list(P.u16le(v))
        self.send(P.packet(P.Cmd.SET_SLEEPTIME, data=vals))
        sleep_ms(500)

    def get_options(self) -> KeyboardOptions:
        r = self._get(P.Cmd.GET_KBOPTION, self.profile)
        b, f, ps = r[2], r[3], r[4]
        return KeyboardOptions(
            win_lock=bool(b & 1), mac_mode=bool(b & 6), wasd_arrows_swap=bool(b & 8),
            led_off=bool(b & 16), side_led_off=bool(b & 32), keyboard_mode=bool(b & 64),
            keyboard_lock=bool(b & 128), fn_matrix=bool(f & 1), power_save=bool(ps), raw=(b, f, ps))

    def set_options(self, o: KeyboardOptions) -> None:
        b = (int(o.win_lock) | int(o.mac_mode) << 2 | int(o.wasd_arrows_swap) << 3 | int(o.led_off) << 4
             | int(o.side_led_off) << 5 | int(o.keyboard_mode) << 6 | int(o.keyboard_lock) << 7)
        self.send(P.packet(P.Cmd.SET_KBOPTION, self.profile, b, int(o.fn_matrix), int(o.power_save)))
        sleep_ms(200)

    def factory_reset(self) -> None:
        self.send(P.packet(P.Cmd.SET_RESET))
        self.profile = 0
        sleep_ms(1500)

    # ------------------------------------------------------------ luces
    def get_light(self) -> L.LightSetting:
        return L.decode_light(self._get(P.Cmd.GET_LEDPARAM))

    def set_light(self, s: L.LightSetting) -> None:
        self.send(L.encode_light(s), checksum=None)  # ya lleva checksum BIT8
        sleep_ms(300)

    def get_side_light(self) -> L.LightSetting:
        return L.decode_side(self._get(P.Cmd.GET_SLEDPARAM))

    def set_side_light(self, s: L.LightSetting) -> None:
        self.send(L.encode_side(s), checksum=None)
        sleep_ms(300)

    def set_key_color(self, key: PhysicalKey | int, rgb: int, layer: int = 0) -> None:
        """Color de una tecla en el modo 'Imagen de usuario'."""
        slot = key if isinstance(key, int) else key.slot
        self.send(P.packet(P.Cmd.SET_USERPIC_SIMPLE, layer, slot,
                           data=[(rgb >> 16) & 0xFF, (rgb >> 8) & 0xFF, rgb & 0xFF]))

    def get_key_colors(self) -> list[int]:
        """Colores por slot (128) de la imagen de usuario activa."""
        data = b""
        for page in range(6):
            data += self._get(P.Cmd.GET_USERPIC, 0, page)
        return [(data[i] << 16) | (data[i + 1] << 8) | data[i + 2] for i in range(0, P.MATRIX_SLOTS * 3, 3)]

    # ------------------------------------------------------------ teclas
    def read_matrix(self, profile: int | None = None, fn: bool = False,
                    progress: Progress | None = None) -> list[Action]:
        prof = self.profile if profile is None else profile
        cmd = P.Cmd.GET_FN_KEYMATRIX if fn else P.Cmd.GET_KEYMATRIX
        data = b""
        for page in range(8):
            data += self._get(cmd, 0 if fn else prof, page)
            if progress:
                progress((page + 1) / 8, "leyendo teclas")
        return matrix_to_actions(data)

    def set_key(self, key: PhysicalKey | int, action: Action, profile: int | None = None, fn: bool = False) -> None:
        slot = key if isinstance(key, int) else key.slot
        if not 0 <= slot < P.MATRIX_SLOTS:
            raise ValueError("slot fuera de rango")
        if fn:
            buf = P.packet(P.Cmd.SET_FN_SIMPLE, 0, slot, data=action.raw)
        else:
            prof = self.profile if profile is None else profile
            buf = P.packet(P.Cmd.SET_KEYMATRIX_SIMPLE, prof, slot, data=action.raw)
        self.send(buf)
        sleep_ms(50)

    # ------------------------------------------------------------ macros
    def read_macro(self, index: int) -> Macro:
        if not 0 <= index < P.MACRO_MAX:
            raise ValueError("macro 0..49")
        data = b""
        for page in range(4):
            data += self._get(P.Cmd.GET_MACRO, index, page)
        return decode_macro(data)

    def write_macro(self, index: int, macro: Macro) -> None:
        if not 0 <= index < P.MACRO_MAX:
            raise ValueError("macro 0..49")
        buf = encode_macro(macro)
        pages = macro_pages(buf)
        for i, page in enumerate(pages):
            last = 1 if i == len(pages) - 1 else 0
            self.send(P.packet(P.Cmd.SET_MACRO_SIMPLE, index, i, 56, last, data=page))
        sleep_ms(50)

    # ------------------------------------------------------------ pantalla
    def sync_clock(self, when: _dt.datetime | None = None) -> _dt.datetime:
        t = when or _dt.datetime.now()
        self.send(P.packet(P.Cmd.SET_OLED_CLOCK, data=[
            (t.year >> 8) & 0xFF, t.year & 0xFF, t.month, t.day, t.hour, t.minute, t.second]))
        return t

    def upload_animation(self, anim: lcd.Animation, progress: Progress | None = None,
                         cancel: Callable[[], bool] | None = None) -> None:
        """Sube una imagen o GIF a la pantalla (solo por cable)."""
        if self.bus == "bt":
            raise TransportError("la subida de imagenes solo funciona por cable "
                                 "(el driver oficial tampoco la permite por Bluetooth)")
        frames = anim.frames
        n = len(frames)
        if not 1 <= n <= P.LCD_MAX_FRAMES:
            raise ValueError(f"de 1 a {P.LCD_MAX_FRAMES} cuadros")
        box = lcd.content_box(frames)
        datas = [lcd.frame_to_rgb565(f, box) for f in frames]
        size = len(datas[0])
        with self._lock:
            hdr = lcd.header_packet(n, anim.delay_ms, size, box)
            ready = False
            for _ in range(11):
                r = self.query(hdr, checksum=None, read_delay_ms=100)
                if r[1] == 1 or self.is_dry_run:
                    ready = True
                    break
                sleep_ms(100)
            if not ready:
                raise TransportError("la pantalla no respondio 'listo'. ¿Esta encendida? Prueba Fn+Ctrl y reintenta.")
            sleep_ms(100)
            total = sum((len(d) + 55) // 56 for d in datas)
            sent = 0
            for fi, data in enumerate(datas):
                for pkt in lcd.data_packets(data, fi, n, anim.delay_ms):
                    if cancel and cancel():
                        raise TransportError("subida cancelada")
                    self.send(pkt, checksum=None, delay_ms=1)
                    sent += 1
                    if progress and (sent % 32 == 0 or sent == total):
                        progress(sent / total, f"cuadro {fi + 1}/{n}")
