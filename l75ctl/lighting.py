"""Efectos de iluminacion (teclas y tira lateral) del L75.

Paquete de luz de teclas (cmd 0x07, checksum BIT8):
  [0x07, modo, 4 - velocidad, brillo, (opcion << 4) | color, R, G, B]
  color = 8 -> arcoiris ("dazzle"), 7 -> color fijo (R, G, B),
  0..6 -> color predefinido.

Tira lateral (cmd 0x08, checksum BIT8): igual pero la velocidad va directa.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import protocol as P

MAX_SPEED = 4
MAX_BRIGHTNESS = 4
DAZZLE = 8
NORMAL = 7

PRESET_COLORS = {
    0: 0xFF0000, 1: 0xFF8000, 2: 0xFFFF00, 3: 0x00FF00,
    4: 0x00FFFF, 5: 0x0000FF, 6: 0xFF00FF,
}


@dataclass(frozen=True)
class ModeDef:
    key: str
    code: int
    label: str
    speed: bool = True
    color: bool = True
    options: tuple[str, ...] = ()
    option_labels: tuple[str, ...] = ()
    kind: str = "normal"  # normal | music | picture | screen | off


_DIR = ("right", "left", "down", "up")
_DIR_L = ("derecha", "izquierda", "abajo", "arriba")
_MUSIC = ("upright", "separate", "intersect")
_MUSIC_L = ("vertical", "separado", "cruzado")

# Modos que el driver oficial ofrece para el L75 (layout "lightK401t").
MODES: list[ModeDef] = [
    ModeDef("off", 0, "Apagado", speed=False, color=False, kind="off"),
    ModeDef("static", 1, "Fijo", speed=False),
    ModeDef("breath", 2, "Respiracion"),
    ModeDef("neon", 3, "Neon", color=False),
    ModeDef("wave", 4, "Ola", options=_DIR, option_labels=_DIR_L),
    ModeDef("ripple", 5, "Onda expansiva"),
    ModeDef("raindrop", 6, "Gotas de lluvia"),
    ModeDef("snake", 7, "Serpiente", options=("z", "return"), option_labels=("en Z", "ida y vuelta")),
    ModeDef("reactive", 8, "Reactivo (se enciende al pulsar)"),
    ModeDef("converge", 9, "Convergencia"),
    ModeDef("sine", 10, "Onda senoidal"),
    ModeDef("kaleidoscope", 11, "Caleidoscopio", options=("out", "in"), option_labels=("hacia fuera", "hacia dentro")),
    ModeDef("linewave", 12, "Linea", options=("right", "left"), option_labels=("derecha", "izquierda")),
    ModeDef("user", 13, "Imagen de usuario (colores por tecla)", speed=False, color=False, kind="picture"),
    ModeDef("laser", 14, "Laser"),
    ModeDef("circle", 15, "Circulo", options=("anti-clockwise", "clockwise"), option_labels=("antihorario", "horario")),
    ModeDef("dazzling", 16, "Deslumbrante"),
    ModeDef("raindown", 17, "Lluvia"),
    ModeDef("meteor", 18, "Meteoro"),
    ModeDef("reactive-off", 19, "Reactivo inverso (se apaga al pulsar)"),
    ModeDef("music3", 20, "Musica 1", speed=False, options=_MUSIC, option_labels=_MUSIC_L, kind="music"),
    ModeDef("screen", 21, "Color de pantalla", speed=False, color=False, kind="screen"),
    ModeDef("music2", 22, "Musica 2", speed=False, options=_MUSIC, option_labels=_MUSIC_L, kind="music"),
]
MODE_BY_KEY = {m.key: m for m in MODES}
MODE_BY_CODE = {m.code: m for m in MODES}

# Tira lateral (RGB light strip)
SIDE_MODES: list[ModeDef] = [
    ModeDef("off", 0, "Apagado", speed=False, color=False, kind="off"),
    ModeDef("static", 1, "Fijo", speed=False),
    ModeDef("breath", 2, "Respiracion"),
    ModeDef("neon", 3, "Neon", color=False),
    ModeDef("wave", 4, "Ola", options=_DIR, option_labels=_DIR_L),
    ModeDef("snake", 5, "Serpiente", options=("z", "return"), option_labels=("en Z", "ida y vuelta")),
]
SIDE_MODE_BY_KEY = {m.key: m for m in SIDE_MODES}
SIDE_MODE_BY_CODE = {m.code: m for m in SIDE_MODES}


@dataclass
class LightSetting:
    mode: str = "static"
    brightness: int = 4          # 0..4
    speed: int = 2               # 0..4 (4 = mas rapido)
    color: int = 0xFFFFFF        # 0xRRGGBB
    rainbow: bool = False        # "dazzle": colores ciclicos
    option: str | None = None    # direccion/variante, o capa 1..5 en modo "user"

    def describe(self, side: bool = False) -> str:
        table = SIDE_MODE_BY_KEY if side else MODE_BY_KEY
        m = table.get(self.mode)
        name = m.label if m else self.mode
        parts = [name]
        if m and m.kind != "off":
            parts.append(f"brillo {self.brightness}/4")
            if m.speed:
                parts.append(f"velocidad {self.speed}/4")
            if m.color:
                parts.append("arcoiris" if self.rainbow else f"color #{self.color:06X}")
            if self.option:
                parts.append(f"opcion {self.option}")
        return ", ".join(parts)


def _clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, int(v)))


def _rgb_bytes(color: int) -> tuple[int, int, int]:
    if color == 0xFFFFFF:
        color = 0xFAFFFA  # el driver oficial hace esta correccion de blanco
    return (color >> 16) & 0xFF, (color >> 8) & 0xFF, color & 0xFF


def encode_light(s: LightSetting) -> bytearray:
    m = MODE_BY_KEY.get(s.mode)
    if m is None:
        raise ValueError("modo desconocido: " + s.mode)
    flag = DAZZLE if s.rainbow else NORMAL
    speed = 0
    bright = 0
    flags = NORMAL
    if m.kind == "off":
        pass
    elif m.kind == "screen":
        bright = 4
    elif m.kind == "picture":
        layer = _clamp(int(s.option or 1), 1, 5)
        flags = (layer - 1) * 16
        bright = _clamp(s.brightness, 0, MAX_BRIGHTNESS)
    elif m.kind == "music":
        opt = m.options.index(s.option) if s.option in m.options else 0
        flags = (opt << 4) | (0 if s.rainbow else 4)
        bright = _clamp(s.brightness, 0, MAX_BRIGHTNESS)
    else:
        bright = _clamp(s.brightness, 0, MAX_BRIGHTNESS)
        if m.speed:
            speed = _clamp(s.speed, 0, MAX_SPEED)
        if m.key == "neon":
            flags = NORMAL
        else:
            opt = m.options.index(s.option) if (m.options and s.option in m.options) else 0
            flags = (opt << 4) | flag
    buf = P.packet(P.Cmd.SET_LEDPARAM, m.code, MAX_SPEED - speed, bright, flags)
    if m.color or m.kind == "music":
        buf[5:8] = bytes(_rgb_bytes(s.color))
    if m.kind == "picture":
        buf[5:8] = bytes((0, 200, 200))
    return P.apply_checksum(buf, P.Checksum.BIT8)


def decode_light(r: bytes) -> LightSetting:
    code, speed_raw, bright, flags = r[1], r[2], r[3], r[4]
    color = (r[5] << 16) | (r[6] << 8) | r[7]
    if color == 0xFAFFFA:
        color = 0xFFFFFF
    m = MODE_BY_CODE.get(code)
    if m is None:
        return LightSetting(mode=f"code{code}", brightness=bright, speed=0, color=color)
    opt_idx, cflag = flags >> 4, flags & 0x0F
    s = LightSetting(mode=m.key, brightness=bright, speed=_clamp(MAX_SPEED - speed_raw, 0, MAX_SPEED), color=color)
    if m.kind == "picture":
        s.option = str(_clamp(flags // 16 + 1, 1, 5))
        return s
    if m.kind == "music":
        s.rainbow = cflag == 0
    else:
        s.rainbow = cflag == DAZZLE
        if cflag not in (DAZZLE, NORMAL) and cflag in PRESET_COLORS:
            s.color = PRESET_COLORS[cflag]
    if m.options:
        s.option = m.options[opt_idx] if opt_idx < len(m.options) else m.options[0]
    if not m.speed:
        s.speed = 0
    return s


def encode_side(s: LightSetting) -> bytearray:
    m = SIDE_MODE_BY_KEY.get(s.mode)
    if m is None:
        raise ValueError("modo de tira lateral desconocido: " + s.mode)
    flag = DAZZLE if s.rainbow else NORMAL
    speed = _clamp(s.speed, 0, MAX_SPEED) if m.speed else 0
    bright = _clamp(s.brightness, 0, MAX_BRIGHTNESS) if m.kind != "off" else 0
    flags = NORMAL
    if m.key in ("static", "breath"):
        flags = flag
    elif m.key == "wave":
        opt = m.options.index(s.option) if s.option in m.options else 0
        flags = (opt << 4) | flag
    elif m.key == "snake":
        flags = (16 if s.option == "return" else 0) | flag
    buf = P.packet(P.Cmd.SET_SLEDPARAM, m.code, speed, bright, flags)
    if m.color:
        buf[5:8] = bytes(_rgb_bytes(s.color))
    return P.apply_checksum(buf, P.Checksum.BIT8)


def decode_side(r: bytes) -> LightSetting:
    code, speed, bright, flags = r[1], r[2], r[3], r[4]
    color = (r[5] << 16) | (r[6] << 8) | r[7]
    if color == 0xFAFFFA:
        color = 0xFFFFFF
    m = SIDE_MODE_BY_CODE.get(code)
    if m is None:
        return LightSetting(mode=f"code{code}", brightness=bright, speed=speed, color=color)
    cflag = flags & 0x0F
    s = LightSetting(mode=m.key, brightness=bright, speed=_clamp(speed, 0, MAX_SPEED), color=color,
                     rainbow=cflag == DAZZLE)
    if cflag not in (DAZZLE, NORMAL) and cflag in PRESET_COLORS:
        s.color = PRESET_COLORS[cflag]
    if m.key == "wave":
        idx = flags >> 4
        s.option = m.options[idx] if idx < len(m.options) else "right"
    elif m.key == "snake":
        s.option = "z" if (flags >> 4) == 0 else "return"
    return s


def parse_color(text: str) -> int:
    t = text.strip().lower().lstrip("#")
    names = {"rojo": 0xFF0000, "red": 0xFF0000, "verde": 0x00FF00, "green": 0x00FF00,
             "azul": 0x0000FF, "blue": 0x0000FF, "blanco": 0xFFFFFF, "white": 0xFFFFFF,
             "amarillo": 0xFFFF00, "yellow": 0xFFFF00, "cian": 0x00FFFF, "cyan": 0x00FFFF,
             "morado": 0xFF00FF, "magenta": 0xFF00FF, "naranja": 0xFF8000, "orange": 0xFF8000,
             "negro": 0, "black": 0}
    if t in names:
        return names[t]
    if t.startswith("0x"):
        t = t[2:]
    if len(t) == 3:
        t = "".join(c * 2 for c in t)
    if len(t) != 6:
        raise ValueError(f"color invalido: {text!r} (usa #RRGGBB)")
    return int(t, 16)
