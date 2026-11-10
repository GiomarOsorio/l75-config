"""Codificacion de macros (buffer de 256 bytes), igual que el driver oficial.

Formato:
  bytes 0-1   numero de repeticiones (uint16 LE)
  luego eventos:
    [codigo, attr]           attr bit7 = pulsar(1)/soltar(0)
                             attr bits0-6 = retardo en ms si es <= 127
    [lo, hi]                 retardo uint16 LE (si no cupo en attr)
  codigos: 0x04-0xEF tecla HID, 0xF0-0xF8 boton de raton, 0xF9 movimiento
  de raton seguido de dx, dy.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

from . import protocol as P
from .keymap import hid_name, parse_hid

MOUSE_CODES = {
    "left": 240, "right": 241, "middle": 242, "forward": 243, "back": 244,
    "wheelleft": 245, "wheelright": 246, "wheelforward": 247, "wheelback": 248,
}
MOUSE_NAMES = {v: k for k, v in MOUSE_CODES.items()}


@dataclass
class MacroEvent:
    type: str            # "key", "mouse", "delay", "move"
    value: int = 0       # codigo HID / codigo de raton / ms
    down: bool = True
    dx: int = 0
    dy: int = 0

    def describe(self) -> str:
        if self.type == "delay":
            return f"esperar {self.value} ms"
        if self.type == "move":
            return f"mover raton ({self.dx}, {self.dy})"
        act = "pulsar" if self.down else "soltar"
        if self.type == "mouse":
            return f"{act} raton {MOUSE_NAMES.get(self.value, self.value)}"
        return f"{act} {hid_name(self.value)}"

    def to_text(self) -> str:
        if self.type == "delay":
            return f"delay:{self.value}"
        if self.type == "move":
            return f"move:{self.dx},{self.dy}"
        act = "down" if self.down else "up"
        if self.type == "mouse":
            return f"{act}:mouse-{MOUSE_NAMES.get(self.value, self.value)}"
        return f"{act}:{hid_name(self.value)}"


@dataclass
class Macro:
    events: list[MacroEvent] = field(default_factory=list)
    repeat: int = 1

    def to_text(self) -> str:
        return ", ".join(e.to_text() for e in self.events)


def parse_macro_text(text: str) -> list[MacroEvent]:
    """``down:ctrl, down:c, delay:30, up:c, up:ctrl`` o ``tap:a`` (pulsar+soltar)."""
    events: list[MacroEvent] = []
    for raw in text.replace(";", ",").split(","):
        tok = raw.strip()
        if not tok:
            continue
        kind, _, arg = tok.partition(":")
        kind = kind.lower()
        if kind in ("delay", "wait", "d"):
            events.append(MacroEvent("delay", int(arg)))
        elif kind == "move":
            dx, dy = (int(v) for v in arg.split(","))
            events.append(MacroEvent("move", dx=dx, dy=dy))
        elif kind in ("down", "up", "tap", "press"):
            target = arg.strip()
            if target.lower().startswith("mouse-"):
                code = MOUSE_CODES[target[6:].lower()]
                typ = "mouse"
            else:
                code = parse_hid(target)
                typ = "key"
            if kind in ("tap", "press"):
                events.append(MacroEvent(typ, code, True))
                events.append(MacroEvent(typ, code, False))
            else:
                events.append(MacroEvent(typ, code, kind == "down"))
        else:
            raise ValueError(f"evento de macro desconocido: {tok!r}")
    return events


def encoded_length(events: list[MacroEvent]) -> int:
    return len(_encode(events, 0, check=False))


def _encode(events: list[MacroEvent], repeat: int, check: bool = True) -> bytearray:
    out = bytearray()
    out += struct.pack("<H", repeat & 0xFFFF)
    pending = False  # el ultimo evento no tiene retardo aun
    t = 0
    n = len(events)
    while t < n:
        ev = events[t]
        if ev.type != "delay" and pending:
            out += b"\0\0"
        if ev.type == "delay":
            v = max(0, min(0xFFFF, int(ev.value)))
            if pending:
                out += struct.pack("<H", v)
            else:
                out += b"\0\0" + struct.pack("<H", v)
            pending = False
        else:
            if ev.type == "key":
                out.append(ev.value & 0xFF)
            elif ev.type == "mouse":
                out.append(ev.value & 0xFF)
            elif ev.type == "move":
                out.append(249)
            else:
                raise ValueError(f"tipo de evento invalido: {ev.type}")
            attr = 0
            if t + 1 < n and events[t + 1].type == "delay" and events[t + 1].value <= 127:
                attr = int(events[t + 1].value)
            if ev.type != "move":
                attr = (attr | 0x80) if ev.down else (attr & 0x7F)
            out.append(attr)
            pending = True
            if attr & 0x7F:
                pending = False
                t += 1  # el retardo ya va dentro de attr
            if ev.type == "move":
                out += struct.pack("<bb", max(-128, min(127, ev.dx)), max(-128, min(127, ev.dy)))
        t += 1
    if check and len(out) > P.MACRO_MAX_BYTES:
        raise ValueError(
            f"la macro ocupa {len(out)} bytes; el maximo es {P.MACRO_MAX_BYTES}. "
            "Quita eventos o retardos.")
    return out


def encode_macro(macro: Macro) -> bytes:
    """Devuelve el buffer de 256 bytes listo para enviar."""
    body = _encode(macro.events, macro.repeat)
    return bytes(body).ljust(P.MACRO_BUFFER, b"\0")


def decode_macro(buf: bytes) -> Macro:
    """Inverso de encode_macro (port de buffToMacroEvents del driver)."""
    if len(buf) < 6:
        return Macro([], 0)
    repeat = buf[0] | buf[1] << 8
    events: list[MacroEvent] = []
    n = 2
    a = buf[n:n + 4]
    n += 4
    guard = 0
    while n < len(buf) and len(a) == 4 and guard < 512:
        guard += 1
        if a[0] == 249:
            dx = a[2] - 256 if a[2] > 127 else a[2]
            dy = a[3] - 256 if a[3] > 127 else a[3]
            events.append(MacroEvent("move", dx=dx, dy=dy))
            if a[1] != 0:
                delay = a[1]
            else:
                delay = buf[n] | buf[n + 1] << 8 if n + 1 < len(buf) else 0
                n += 2
            events.append(MacroEvent("delay", delay))
        else:
            down = bool(a[1] & 0x80)
            if 4 <= a[0] <= 239:
                events.append(MacroEvent("key", a[0], down))
            elif a[0] in MOUSE_NAMES:
                events.append(MacroEvent("mouse", a[0], down))
            if a[1] & 0x7F:
                delay = a[1] & 0x7F
                n -= 2
            else:
                delay = a[2] | a[3] << 8
            events.append(MacroEvent("delay", delay))
        a = buf[n:n + 4]
        if bytes(a) == b"\0\0\0\0":
            break
        n += 4
    events = [e for e in events if not (e.type == "delay" and e.value == 0)]
    return Macro(events, repeat)


def macro_pages(buf: bytes) -> list[bytes]:
    """Divide el buffer en paginas de 56 bytes como hace el driver YC500.

    Solo se envian las paginas con datos (minimo 1).
    """
    pages = [bytes(buf[i:i + 56]).ljust(56, b"\0") for i in range(0, 5 * 56, 56)]
    count = sum(1 for p in pages if any(p))
    count = max(1, count)
    return pages[:count]
