"""Acciones de teclas: codificacion de 4 bytes usada por el firmware.

Cada posicion de la matriz guarda 4 bytes [tipo, a, b, c]:

  [0, 0, hid, 0]          tecla normal (codigo HID)
  [0, m, hid, hid2]       combinacion: hasta 3 codigos HID (m suele ser un
                          modificador: 0xE0 Ctrl, 0xE1 Shift, 0xE2 Alt, 0xE3 Win)
  [1, 0, btn, x]          boton / rueda del raton
  [3, 0, lo, hi]          tecla multimedia (Consumer usage, little endian)
  [9, modo, n, 0]         macro n (modo 0=repetir N veces, 1=on/off, 2=mientras se mantiene)
  [10, 1, 0, 0]           Fn
  [0, 0, 0, 0]            desactivada
"""

from __future__ import annotations

from dataclasses import dataclass

from .i18n import t as _t
from .l75_data import DEFAULT_MATRIX, LAYOUT

# ---------------------------------------------------------------- HID names
HID_NAMES: dict[int, str] = {}
for _i, _c in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ"):
    HID_NAMES[0x04 + _i] = _c
for _i, _c in enumerate("1234567890"):
    HID_NAMES[0x1E + _i] = _c
HID_NAMES.update({
    0x28: "Enter", 0x29: "Esc", 0x2A: "Backspace", 0x2B: "Tab", 0x2C: "Space",
    0x2D: "-", 0x2E: "=", 0x2F: "[", 0x30: "]", 0x31: "\\", 0x32: "#ISO",
    0x33: ";", 0x34: "'", 0x35: "`", 0x36: ",", 0x37: ".", 0x38: "/",
    0x39: "CapsLock",
    0x46: "PrintScreen", 0x47: "ScrollLock", 0x48: "Pause", 0x49: "Insert",
    0x4A: "Home", 0x4B: "PageUp", 0x4C: "Delete", 0x4D: "End", 0x4E: "PageDown",
    0x4F: "Right", 0x50: "Left", 0x51: "Down", 0x52: "Up",
    0x53: "NumLock", 0x54: "KP/", 0x55: "KP*", 0x56: "KP-", 0x57: "KP+", 0x58: "KPEnter",
    0x59: "KP1", 0x5A: "KP2", 0x5B: "KP3", 0x5C: "KP4", 0x5D: "KP5", 0x5E: "KP6",
    0x5F: "KP7", 0x60: "KP8", 0x61: "KP9", 0x62: "KP0", 0x63: "KP.",
    0x64: "\\ISO", 0x65: "Menu",
    0x87: "Ro", 0x88: "Kana", 0x89: "Yen", 0x8A: "Henkan", 0x8B: "Muhenkan",
    0xE0: "Ctrl", 0xE1: "Shift", 0xE2: "Alt", 0xE3: "Win",
    0xE4: "RCtrl", 0xE5: "RShift", 0xE6: "RAlt", 0xE7: "RWin",
})
for _i in range(12):
    HID_NAMES[0x3A + _i] = f"F{_i + 1}"
for _i in range(12):
    HID_NAMES[0x68 + _i] = f"F{_i + 13}"

_ALIASES = {
    "escape": 0x29, "return": 0x28, "bksp": 0x2A, "backspace": 0x2A, "spacebar": 0x2C,
    "space": 0x2C, "caps": 0x39, "capslock": 0x39, "del": 0x4C, "ins": 0x49,
    "pgup": 0x4B, "pgdn": 0x4E, "pagedown": 0x4E, "pageup": 0x4B,
    "lctrl": 0xE0, "control": 0xE0, "ctrl": 0xE0, "lshift": 0xE1, "shift": 0xE1,
    "lalt": 0xE2, "alt": 0xE2, "lwin": 0xE3, "win": 0xE3, "super": 0xE3, "meta": 0xE3,
    "gui": 0xE3, "cmd": 0xE3, "rctrl": 0xE4, "rshift": 0xE5, "ralt": 0xE6, "altgr": 0xE6,
    "rwin": 0xE7, "rsuper": 0xE7, "minus": 0x2D, "equal": 0x2E, "grave": 0x35,
    "backslash": 0x31, "slash": 0x38, "comma": 0x36, "period": 0x37, "dot": 0x37,
    "semicolon": 0x33, "quote": 0x34, "lbracket": 0x2F, "rbracket": 0x30,
    "prtsc": 0x46, "print": 0x46, "up": 0x52, "down": 0x51, "left": 0x50, "right": 0x4F,
    "ñ": 0x33,
}
NAME_TO_HID: dict[str, int] = {v.lower(): k for k, v in HID_NAMES.items()}
NAME_TO_HID.update(_ALIASES)


def hid_name(code: int) -> str:
    return HID_NAMES.get(code, f"0x{code:02X}")


def parse_hid(name: str) -> int:
    s = name.strip()
    if s.lower().startswith("0x"):
        return int(s, 16)
    if s.isdigit() and len(s) > 1:
        return int(s)
    try:
        return NAME_TO_HID[s.lower()]
    except KeyError:
        raise ValueError(_t("unknown key: {name}").format(name=repr(name))) from None


# ---------------------------------------------------------------- funciones
# (key, English label -> translated with _t(), bytes). From the official driver table.
FUNCTIONS: list[tuple[str, str, tuple[int, int, int, int]]] = [
    ("play", "Play/Pause", (3, 0, 205, 0)),
    ("stop", "Stop", (3, 0, 183, 0)),
    ("prev", "Previous track", (3, 0, 182, 0)),
    ("next", "Next track", (3, 0, 181, 0)),
    ("mute", "Mute", (3, 0, 226, 0)),
    ("vol-", "Volume -", (3, 0, 234, 0)),
    ("vol+", "Volume +", (3, 0, 233, 0)),
    ("player", "Media player", (3, 0, 131, 1)),
    ("calc", "Calculator", (3, 0, 146, 1)),
    ("mail", "Mail", (3, 0, 138, 1)),
    ("mycomputer", "My computer / Files", (3, 0, 148, 1)),
    ("search", "Search", (3, 0, 33, 2)),
    ("home", "Browser home", (3, 0, 35, 2)),
    ("back", "Browser back", (3, 0, 36, 2)),
    ("refresh", "Refresh", (3, 0, 39, 2)),
    ("bright-", "Screen brightness -", (3, 0, 112, 0)),
    ("bright+", "Screen brightness +", (3, 0, 111, 0)),
    ("fn", "Fn", (10, 1, 0, 0)),
    ("lock", "Lock session (Win+L)", (0, 0, 227, 15)),
    ("zoom-", "Zoom out (Win+-)", (0, 0, 227, 45)),
    ("zoom+", "Zoom in (Win+=)", (0, 0, 227, 46)),
    ("ime", "Switch input language (Ctrl+Space)", (0, 224, 44, 0)),
    ("(", "Parenthesis (", (0, 0, 229, 38)),
    (")", "Parenthesis )", (0, 0, 229, 39)),
    ("{", "Brace {", (0, 225, 47, 0)),
    ("}", "Brace }", (0, 225, 48, 0)),
]
FUNCTION_BY_KEY = {k: (label, b) for k, label, b in FUNCTIONS}
FUNCTION_BY_BYTES = {b: k for k, _l, b in FUNCTIONS}

# Mouse (table used when remapping keys on the YC500 series).
MOUSE: list[tuple[str, str, tuple[int, int, int, int]]] = [
    ("left", "Left click", (1, 0, 240, 0)),
    ("right", "Right click", (1, 0, 241, 0)),
    ("middle", "Middle click", (1, 0, 242, 0)),
    ("forward", "Forward", (1, 0, 244, 0)),
    ("back", "Back", (1, 0, 243, 0)),
    ("wheelup", "Wheel up", (1, 0, 245, 1)),
    ("wheeldown", "Wheel down", (1, 0, 245, 255)),
]
MOUSE_BY_KEY = {k: (label, b) for k, label, b in MOUSE}
MOUSE_BY_BYTES = {b: k for k, _l, b in MOUSE}

MACRO_MODES = {"times": 0, "toggle": 1, "hold": 2}
MACRO_MODE_LABELS = {0: "repeat N times", 1: "on/off (press to start/stop)", 2: "while held"}
MODIFIER_HIDS = range(0xE0, 0xE8)

# Fn-layer system functions (read from a real L75; names from the official manual).
# The official driver does not let you change them ("系统按键无法修改": system key).
# (short, description, confirmed in the manual)
SYSTEM_FUNCTIONS: dict[tuple[int, int, int, int], tuple[str, str, bool]] = {
    (10, 1, 0, 0): ("Fn", "Fn", True),
    (10, 1, 1, 0): ("Fn", "Right Fn", True),
    (10, 2, 0, 0): ("Reset", "Reset the keyboard", True),
    (10, 3, 0, 0): ("WinLk", "Lock the Windows key", False),
    (10, 5, 0, 0): ("Win", "Windows layout", True),
    (10, 5, 1, 0): ("Mac", "Mac layout", True),
    (10, 5, 2, 0): ("iOS", "iOS layout", True),
    (10, 8, 0, 0): ("Bat", "Battery indicator", True),
    (10, 12, 0, 0): ("Light", "Turn the lighting on / off", True),
    (10, 13, 0, 0): ("FnLk", "Fn Lock", False),
    (13, 1, 0, 0): ("Mode", "Next lighting effect", True),
    (13, 2, 1, 0): ("Br+", "Lighting brightness up", True),
    (13, 2, 2, 0): ("Br−", "Lighting brightness down", True),
    (13, 3, 1, 0): ("Spd−", "Lighting speed down", True),
    (13, 3, 2, 0): ("Spd+", "Lighting speed up", True),
    (13, 5, 1, 0): ("Color", "Next lighting colour (single colour)", True),
    (13, 8, 0, 0): ("Strip", "Side strip mode / off", False),
    (14, 0, 0, 0): ("BT1", "Bluetooth channel 1 (hold: pair)", True),
    (14, 0, 1, 0): ("BT2", "Bluetooth channel 2 (hold: pair)", True),
    (14, 0, 2, 0): ("BT3", "Bluetooth channel 3 (hold: pair)", True),
    (14, 0, 5, 0): ("2.4G", "2.4 GHz channel", False),
    (19, 0, 0, 0): ("LCD", "Screen: your image or the default style", True),
    (19, 2, 0, 0): ("LCD2", "Screen: another view", False),
}
SYSTEM_TYPES = (2, 8, 10, 13, 14, 18, 19)


def is_system(raw: tuple[int, int, int, int]) -> bool:
    """Firmware system function: the official driver does not let you change it."""
    return raw in SYSTEM_FUNCTIONS or raw[0] in SYSTEM_TYPES


# ---------------------------------------------------------------- acciones
@dataclass(frozen=True)
class Action:
    raw: tuple[int, int, int, int]

    @property
    def kind(self) -> str:
        t, a, b, c = self.raw
        if self.raw == (0, 0, 0, 0):
            return "off"
        if self.raw[0] in SYSTEM_TYPES and self.raw not in ((10, 1, 0, 0), (10, 1, 1, 0)):
            return "system"
        if self.raw in FUNCTION_BY_BYTES:
            return "function"
        if t == 0:
            return "key" if (a == 0 and c == 0) else "combo"
        if t == 1:
            return "mouse"
        if t == 3:
            return "media"
        if t == 9:
            return "macro"
        if t == 10:
            return "fn"
        return "unknown"

    def describe(self) -> str:
        t, a, b, c = self.raw
        k = self.kind
        if k == "off":
            return _t("(disabled)")
        if k == "function":
            return _t(FUNCTION_BY_KEY[FUNCTION_BY_BYTES[self.raw]][0])
        if k == "key":
            return hid_name(b)
        if k == "combo":
            return "+".join(hid_name(x) for x in (a, b, c) if x)
        if k == "mouse":
            key = MOUSE_BY_BYTES.get(self.raw)
            return _t("Mouse: {what}").format(what=_t(MOUSE_BY_KEY[key][0]) if key else f"{b},{c}")
        if k == "media":
            return _t("Media 0x{code}").format(code=f"{b | c << 8:03X}")
        if k == "macro":
            return _t("Macro {n} ({mode})").format(n=b, mode=_t(MACRO_MODE_LABELS[a]) if a in MACRO_MODE_LABELS else a)
        if k == "fn":
            return "Fn" if a == 1 else _t("Special Fn {a},{b}").format(a=a, b=b)
        if k == "system":
            info = SYSTEM_FUNCTIONS.get(self.raw)
            if info:
                return _t(info[1]) + ("" if info[2] else " " + _t("(unconfirmed)"))
            return _t("System function") + " [" + ",".join(str(x) for x in self.raw) + "]"
        return _t("Unknown") + " [" + ",".join(str(x) for x in self.raw) + "]"

    def short(self) -> str:
        k = self.kind
        t, a, b, c = self.raw
        if k == "key":
            return hid_name(b)
        if k == "off":
            return "—"
        if k == "macro":
            return f"M{b}"
        if k == "function":
            return FUNCTION_BY_BYTES[self.raw]
        if k == "combo":
            return "+".join(_short_mod(x) for x in (a, b, c) if x)
        if k == "mouse":
            return "🖱" + (MOUSE_BY_BYTES.get(self.raw) or "?")
        if k == "fn":
            return "Fn"
        if k == "system":
            info = SYSTEM_FUNCTIONS.get(self.raw)
            return _t(info[0]) if info else _t("Sys.")
        return self.describe()[:6]

    # ---- constructores
    @staticmethod
    def key(hid: int) -> "Action":
        return Action((0, 0, hid & 0xFF, 0))

    @staticmethod
    def combo(codes: list[int]) -> "Action":
        if not 1 <= len(codes) <= 3:
            raise ValueError(_t("a combination takes 1 to 3 keys"))
        if len(codes) == 1:
            return Action.key(codes[0])
        # Formato del driver: [0, modificador, tecla, tecla2]
        mods = [x for x in codes if x in MODIFIER_HIDS]
        rest = [x for x in codes if x not in MODIFIER_HIDS]
        ordered = mods + rest
        if len(ordered) == 2:
            return Action((0, ordered[0], ordered[1], 0))
        return Action((0, ordered[0], ordered[1], ordered[2]))

    @staticmethod
    def macro(index: int, mode: int = 0) -> "Action":
        if not 0 <= index < 50:
            raise ValueError(_t("macro index 0..49"))
        return Action((9, mode, index, 0))

    @staticmethod
    def disabled() -> "Action":
        return Action((0, 0, 0, 0))


def _short_mod(code: int) -> str:
    return {0xE0: "C", 0xE1: "S", 0xE2: "A", 0xE3: "W", 0xE4: "RC", 0xE5: "RS", 0xE6: "RA", 0xE7: "RW"}.get(
        code, hid_name(code))


def parse_action(text: str) -> Action:
    """Parses command-line actions.

    Examples: ``key:Esc``, ``Esc``, ``combo:ctrl+c``, ``media:vol+``,
    ``fn:play``, ``mouse:left``, ``macro:3``, ``macro:3:hold``, ``off``,
    ``raw:0,0,41,0``.
    """
    s = text.strip()
    kind, _, arg = s.partition(":")
    kind_l = kind.lower()
    if not arg and kind_l not in ("off", "disable", "none", "default"):
        # no prefix: key or combination
        if "+" in s and len(s) > 1:
            return Action.combo([parse_hid(x) for x in s.split("+")])
        if s.lower() in FUNCTION_BY_KEY:
            return Action(FUNCTION_BY_KEY[s.lower()][1])
        return Action.key(parse_hid(s))
    if kind_l in ("off", "disable", "none"):
        return Action.disabled()
    if kind_l == "key":
        return Action.key(parse_hid(arg))
    if kind_l == "combo":
        return Action.combo([parse_hid(x) for x in arg.split("+")])
    if kind_l in ("media", "fn", "func", "function"):
        a = arg.lower()
        if a not in FUNCTION_BY_KEY:
            raise ValueError(_t("unknown function. Options: ") + ", ".join(FUNCTION_BY_KEY))
        return Action(FUNCTION_BY_KEY[a][1])
    if kind_l == "mouse":
        a = arg.lower()
        if a not in MOUSE_BY_KEY:
            raise ValueError(_t("unknown button. Options: ") + ", ".join(MOUSE_BY_KEY))
        return Action(MOUSE_BY_KEY[a][1])
    if kind_l == "macro":
        idx, _, mode = arg.partition(":")
        m = MACRO_MODES.get(mode.lower(), 0) if mode else 0
        return Action.macro(int(idx), m)
    if kind_l == "raw":
        parts = [int(x, 0) for x in arg.replace(" ", "").split(",")]
        if len(parts) != 4:
            raise ValueError(_t("raw needs 4 bytes"))
        return Action(tuple(p & 0xFF for p in parts))  # type: ignore[arg-type]
    raise ValueError(_t("unknown action type: {kind}").format(kind=kind))


# ---------------------------------------------------------------- teclas fisicas
@dataclass(frozen=True)
class PhysicalKey:
    name: str          # printed name
    slot: int          # position in the matrix (0..127)
    x: int
    y: int
    w: int
    h: int

    @property
    def default_action(self) -> Action:
        return Action(DEFAULT_MATRIX[self.slot])


_DISPLAY = {
    "(space)": "Space", "r_Shift": "RShift", "r_Alt": "RAlt", "r_Ctrl": "RCtrl", "FN": "Fn",
    "BackSpace": "Backspace", "Page\nUp": "PgUp", "Page\nDown": "PgDn", "Caps Lock": "CapsLock",
    "Insert": "Ins", "Delete": "Del",
}


def _build_keys() -> list[PhysicalKey]:
    keys = []
    for name, value, x, y, w, h in LAYOUT:
        if value > 0xFF:
            raw = ((value >> 24) & 0xFF, (value >> 16) & 0xFF, (value >> 8) & 0xFF, value & 0xFF)
        else:
            raw = (0, 0, value, 0)
        slot = DEFAULT_MATRIX.index(raw)
        keys.append(PhysicalKey(_DISPLAY.get(name, name.replace("\n", " ")), slot, x, -y, w, h))
    return keys


KEYS: list[PhysicalKey] = _build_keys()
KEY_BY_SLOT = {k.slot: k for k in KEYS}


def find_key(name: str) -> PhysicalKey:
    """Finds a physical key by printed name, HID name or slot number."""
    s = name.strip()
    if s.lower().startswith("slot"):
        slot = int(s[4:].lstrip(":= "))
        if slot in KEY_BY_SLOT:
            return KEY_BY_SLOT[slot]
        raise ValueError(_t("no physical key in slot {slot}").format(slot=slot))
    norm = s.lower().replace(" ", "").replace("_", "")
    for k in KEYS:
        if k.name.lower().replace(" ", "").replace("_", "") == norm:
            return k
    if norm == "fn":
        return next(k for k in KEYS if k.default_action.raw == (10, 1, 0, 0))
    try:
        code = parse_hid(s)
    except ValueError:
        raise ValueError(_t("key not found: {name}").format(name=repr(name))) from None
    for k in KEYS:
        if k.default_action.raw == (0, 0, code, 0):
            return k
    raise ValueError(_t("the L75 has no key {name}").format(name=repr(name)))


def matrix_to_actions(data: bytes) -> list[Action]:
    return [Action(tuple(data[i:i + 4])) for i in range(0, min(len(data), 512), 4)]  # type: ignore[arg-type]
