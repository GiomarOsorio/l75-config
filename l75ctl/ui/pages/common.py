"""Piezas compartidas por las páginas."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QPainter, QPen
from PySide6.QtWidgets import QComboBox, QCompleter, QFrame, QWidget

from ... import lighting as L
from ...i18n import t as tr
from ...keymap import HID_NAMES
from .. import widgets as W
from ..theme import paint_rgb_line, theme

_MODE_HINTS = {
    "reactive": "Lights up when pressed", "reactive-off": "Turns off when pressed",
    "music3": "Follows the computer's audio", "music2": "Follows the computer's audio",
    "user": "Colours from «Per-key colours»", "screen": "Takes the colour of the screen",
}
_OPTION_NAMES = {
    "right": "Right", "left": "Left", "down": "Down", "up": "Up", "z": "Z pattern", "return": "Back and forth",
    "out": "Outwards", "in": "Inwards", "anti-clockwise": "Counter-clockwise", "clockwise": "Clockwise",
    "upright": "Upright", "separate": "Separate", "intersect": "Crossed",
}


def mode_name(key: str, side: bool = False) -> str:
    table = L.SIDE_MODE_BY_KEY if side else L.MODE_BY_KEY
    m = table.get(key) or L.MODE_BY_KEY.get(key)
    return tr(m.label) if m else key


def mode_hint(key: str) -> str:
    h = _MODE_HINTS.get(key)
    return tr(h) if h else ""


def option_name(key: str) -> str:
    n = _OPTION_NAMES.get(key)
    return tr(n) if n else key


OPTION_ICONS = {
    "right": "flecha-derecha", "left": "flecha-izquierda", "down": "flecha-abajo", "up": "flecha-arriba",
    "z": "en-z", "return": "ida-vuelta", "out": "hacia-fuera", "in": "hacia-dentro",
    "anti-clockwise": "antihorario", "clockwise": "horario", "upright": "vertical", "separate": "separado",
    "intersect": "cruzado",
}
_COLOR_NAMES = {0xFF0000: "red", 0xFF8000: "orange", 0xFFFF00: "yellow", 0x00FF00: "green", 0x00FFFF: "cyan",
                0x0000FF: "blue", 0xFF00FF: "magenta", 0xFFFFFF: "white"}

KEY_DISPLAY = {"Insert": "Ins", "Delete": "Del", "PageUp": "PgUp", "PageDown": "PgDn", "Right": "→", "Left": "←",
               "Down": "↓", "Up": "↑", "PrintScreen": "PrtSc", "ScrollLock": "ScrLk", "Backspace": "Backspace"}


def key_display(code: int) -> str:
    n = HID_NAMES.get(code, f"0x{code:02X}")
    return KEY_DISPLAY.get(n, n)


def color_name(rgb: int) -> str:
    n = _COLOR_NAMES.get(rgb)
    return tr(n) if n else f"#{rgb:06X}"


def hid_combo(allow_none: bool = False) -> QComboBox:
    """Desplegable con búsqueda de todas las teclas HID."""
    c = QComboBox()
    c.setEditable(True)
    c.setInsertPolicy(QComboBox.NoInsert)
    c.setMaxVisibleItems(14)
    if allow_none:
        c.addItem("—", 0)
    for code in sorted(HID_NAMES):
        c.addItem(key_display(code), code)
    comp = c.completer()
    comp.setCompletionMode(QCompleter.PopupCompletion)
    comp.setFilterMode(Qt.MatchContains)
    comp.setCaseSensitivity(Qt.CaseInsensitive)
    return c


def combo_value(c: QComboBox):
    i = c.findText(c.currentText(), Qt.MatchFixedString)
    return c.itemData(i) if i >= 0 else c.currentData()


class Deck(QFrame):
    """Carcasa del teclado (token deck) con la firma RGB abajo."""

    def __init__(self, glow: bool = True, parent: QWidget | None = None):
        super().__init__(parent)
        self.glow = glow
        theme().changed.connect(self.update)

    def paintEvent(self, _e):
        t = theme()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(t.c("deck-edge"), 1))
        p.setBrush(t.c("deck"))
        p.drawRoundedRect(r, 16, 16)
        if self.glow:
            w = r.width()
            paint_rgb_line(p, QRectF(r.left() + w * 0.24, r.bottom() - 1.5, w * 0.52, 2), 0.75)


class MiniKey(QWidget):
    """Muestra de la leyenda (normal / reasignada / desactivada)."""

    def __init__(self, kind: str = ""):
        super().__init__()
        self.kind = kind
        self.setFixedSize(14, 14)

    def paintEvent(self, _e):
        t = theme()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(0.5, 0.5, 13, 13)
        if self.kind == "locked":
            err = t.c("error")
            p.setPen(QPen(err, 1))
            c = t.c("error-soft")
            p.setBrush(c)
            p.drawRoundedRect(r, 4, 4)
            return
        edge = t.c("key-remap-edge" if self.kind == "remap" else "key-edge")
        p.setPen(QPen(edge, 1))
        p.setBrush(t.c("key-remap-1" if self.kind == "remap" else ("key-off-top" if self.kind == "off" else "key-top-1")))
        p.drawRoundedRect(r, 4, 4)
        if self.kind == "off":
            p.setPen(QPen(t.c("key-off-hatch"), 1.5))
            for x in (-6, -1, 4, 9):
                p.drawLine(int(x), 13, int(x + 13), 0)


def section_label(text: str) -> QWidget:
    return W.label(text.upper(), "label")
