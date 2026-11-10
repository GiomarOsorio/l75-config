"""Traducción de teclas de Qt a códigos HID (para «Capturar» y grabar macros)."""

from __future__ import annotations

from PySide6.QtCore import Qt

_MAP: dict[int, int] = {}
for i in range(26):
    _MAP[int(Qt.Key_A) + i] = 0x04 + i
for i, k in enumerate((Qt.Key_1, Qt.Key_2, Qt.Key_3, Qt.Key_4, Qt.Key_5, Qt.Key_6, Qt.Key_7, Qt.Key_8, Qt.Key_9,
                       Qt.Key_0)):
    _MAP[int(k)] = 0x1E + i
for i in range(24):
    _MAP[int(Qt.Key_F1) + i] = (0x3A + i) if i < 12 else (0x68 + i - 12)
_MAP.update({int(k): v for k, v in {
    Qt.Key_Return: 0x28, Qt.Key_Enter: 0x28, Qt.Key_Escape: 0x29, Qt.Key_Backspace: 0x2A, Qt.Key_Tab: 0x2B,
    Qt.Key_Backtab: 0x2B, Qt.Key_Space: 0x2C, Qt.Key_Minus: 0x2D, Qt.Key_Underscore: 0x2D, Qt.Key_Equal: 0x2E,
    Qt.Key_Plus: 0x2E, Qt.Key_BracketLeft: 0x2F, Qt.Key_BraceLeft: 0x2F, Qt.Key_BracketRight: 0x30,
    Qt.Key_BraceRight: 0x30, Qt.Key_Backslash: 0x31, Qt.Key_Bar: 0x31, Qt.Key_Semicolon: 0x33, Qt.Key_Colon: 0x33,
    Qt.Key_Apostrophe: 0x34, Qt.Key_QuoteDbl: 0x34, Qt.Key_QuoteLeft: 0x35, Qt.Key_AsciiTilde: 0x35,
    Qt.Key_Comma: 0x36, Qt.Key_Less: 0x36, Qt.Key_Period: 0x37, Qt.Key_Greater: 0x37, Qt.Key_Slash: 0x38,
    Qt.Key_Question: 0x38, Qt.Key_CapsLock: 0x39, Qt.Key_Print: 0x46, Qt.Key_ScrollLock: 0x47, Qt.Key_Pause: 0x48,
    Qt.Key_Insert: 0x49, Qt.Key_Home: 0x4A, Qt.Key_PageUp: 0x4B, Qt.Key_Delete: 0x4C, Qt.Key_End: 0x4D,
    Qt.Key_PageDown: 0x4E, Qt.Key_Right: 0x4F, Qt.Key_Left: 0x50, Qt.Key_Down: 0x51, Qt.Key_Up: 0x52,
    Qt.Key_NumLock: 0x53, Qt.Key_Menu: 0x65, Qt.Key_Control: 0xE0, Qt.Key_Shift: 0xE1, Qt.Key_Alt: 0xE2,
    Qt.Key_Meta: 0xE3, Qt.Key_Super_L: 0xE3, Qt.Key_Super_R: 0xE7, Qt.Key_AltGr: 0xE6,
    # símbolos con Shift (teclado US): se graban como su tecla base
    Qt.Key_Exclam: 0x1E, Qt.Key_At: 0x1F, Qt.Key_NumberSign: 0x20, Qt.Key_Dollar: 0x21, Qt.Key_Percent: 0x22,
    Qt.Key_AsciiCircum: 0x23, Qt.Key_Ampersand: 0x24, Qt.Key_Asterisk: 0x25, Qt.Key_ParenLeft: 0x26,
    Qt.Key_ParenRight: 0x27,
}.items()})


def qt_to_hid(event) -> int | None:
    """Código HID de un QKeyEvent, o None si no hay equivalente."""
    key = int(event.key())
    # modificadores: distinguir izquierdo/derecho cuando el sistema lo indica
    if key in (int(Qt.Key_Control), int(Qt.Key_Shift), int(Qt.Key_Alt), int(Qt.Key_Meta)):
        sc = event.nativeScanCode()
        right = sc in (105, 62, 108, 134) or sc in (0x11D, 0x36, 0x138, 0x15C)  # X11/evdev y Windows
        base = _MAP[key]
        return base + 4 if right else base
    return _MAP.get(key)
