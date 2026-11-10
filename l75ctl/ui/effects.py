"""Vistas previas animadas de los efectos de luz (aproximaciones, solo visuales)."""

from __future__ import annotations

import math
import random

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter

from ..keymap import KEYS
from .keyboard_view import CANVAS_H, CANVAS_W
from .theme import theme

_RNG = random.Random(75)
_SEEDS = {k.slot: _RNG.random() for k in KEYS}
_ROWS = sorted({k.y for k in KEYS})
_ORDER = sorted(KEYS, key=lambda k: (_ROWS.index(k.y), k.x if _ROWS.index(k.y) % 2 == 0 else -k.x))
_ORDER_IDX = {k.slot: i for i, k in enumerate(_ORDER)}

# color de demostración de cada tarjeta (None = arcoíris)
DEMO = {
    "static": None, "breath": 0xFFE600, "neon": None, "wave": None, "ripple": 0xD43BFF, "raindrop": None,
    "snake": 0xFF2D6F, "reactive": None, "converge": 0xFF2DB0, "sine": None, "kaleidoscope": None,
    "linewave": 0x22C55E, "user": None, "laser": 0x8B3DFF, "circle": None, "dazzling": None, "raindown": 0x00FF00,
    "meteor": 0x3D7BFF, "reactive-off": None, "music3": None, "screen": None, "music2": None, "off": 0,
}


def _hue(h: float, v: float = 1.0) -> QColor:
    return QColor.fromHsvF(h % 1.0, 0.9, max(0.0, min(1.0, v)))


def _scale(rgb: int | None, v: float, hue: float) -> QColor:
    v = max(0.0, min(1.0, v))
    if rgb is None:
        return _hue(hue, v)
    return QColor(round(((rgb >> 16) & 255) * v), round(((rgb >> 8) & 255) * v), round((rgb & 255) * v))


def key_color(mode: str, k, t: float, rgb: int | None, speed: int = 2, option: str | None = None) -> QColor | None:
    """Color de la tecla `k` en el instante `t`. None = apagada."""
    sp = 0.35 + speed * 0.3
    t *= sp
    x = (k.x + k.w / 2) / CANVAS_W
    y = (k.y + 16) / CANVAS_H
    seed = _SEEDS[k.slot]
    rev = option in ("left", "up", "in", "anti-clockwise", "return")
    if mode == "off":
        return None
    if mode == "static":
        return _scale(rgb, 1, x * 0.85)
    if mode == "breath":
        return _scale(rgb, 0.25 + 0.75 * (0.5 + 0.5 * math.sin(t * 2.2)), t * 0.1)
    if mode == "neon":
        return _hue(t * 0.12 + 0.6)
    if mode == "wave":
        d = (y if option in ("down", "up") else x)
        return _scale(rgb, 0.4 + 0.6 * (0.5 + 0.5 * math.sin((d * 6 + (t if rev else -t) * 3))), d - (t * 0.25 if not rev else -t * 0.25))
    if mode == "ripple":
        d = math.hypot(x - 0.5, (y - 0.5) * 0.45)
        ph = (t * 0.45) % 1.0
        v = math.exp(-((d - ph * 0.7) ** 2) / 0.004)
        return _scale(rgb, 0.12 + v, d * 2 - t * 0.2) if v > 0.02 else _scale(rgb, 0.12, d)
    if mode in ("raindrop", "reactive", "dazzling"):
        period = 2.4 if mode != "dazzling" else 1.2
        ph = (t / period + seed * 7) % 1.0
        v = max(0.0, 1 - ph * 3) if (int(t / period + seed * 7) * 7919 + k.slot) % (5 if mode == "raindrop" else 4) == 0 else 0
        if mode == "dazzling":
            return _hue(seed + math.floor(t / period + seed * 7) * 0.37, 0.25 + 0.75 * (1 - ph))
        return _scale(rgb, 0.08 + v, seed + t * 0.05) if v > 0 else _scale(rgb, 0.08, seed)
    if mode == "reactive-off":
        ph = (t / 2.4 + seed * 7) % 1.0
        hit = (int(t / 2.4 + seed * 7) * 7919 + k.slot) % 5 == 0
        return _scale(rgb, (ph if hit else 1.0), x)
    if mode == "snake":
        n = len(_ORDER)
        head = (t * 18) % n
        i = _ORDER_IDX[k.slot]
        d = (head - i) % n
        return _scale(rgb, 1 - d / 10, i / n) if d < 10 else _scale(rgb, 0.06, i / n)
    if mode == "converge":
        ph = (t * 0.5) % 1.0
        d = abs(x - 0.5)
        v = math.exp(-((d - (0.5 - ph * 0.5)) ** 2) / 0.003)
        return _scale(rgb, 0.1 + v, d)
    if mode == "sine":
        v = 0.5 + 0.5 * math.sin(x * 9 - t * 3 + y * 2)
        return _scale(rgb, 0.2 + 0.8 * v, x + t * 0.05)
    if mode == "kaleidoscope":
        d = math.hypot(x - 0.5, (y - 0.5) * 0.45)
        return _hue(d * 2.2 + (t * 0.3 if rev else -t * 0.3))
    if mode == "linewave":
        pos = (t * 0.45) % 1.2 - 0.1
        if rev:
            pos = 1 - pos
        v = math.exp(-((x - pos) ** 2) / 0.002)
        return _scale(rgb, 0.08 + v, x)
    if mode == "user":
        return _hue(0.83 - x * 0.45 + (0.2 if y > 0.75 and x > 0.8 else 0), 1)
    if mode == "laser":
        row = _ROWS.index(k.y)
        pos = ((t * 0.5 + row * 0.27) % 1.3) - 0.15
        v = math.exp(-((x - pos) ** 2) / 0.003)
        return _scale(rgb, 0.08 + v, x)
    if mode == "circle":
        a = math.atan2((y - 0.5) * 0.45, x - 0.5) / (2 * math.pi)
        return _hue(a + (t * 0.25 if not rev else -t * 0.25))
    if mode == "raindown":
        col = round(k.x / 35)
        ph = (t * 0.55 + _SEEDS.get(col % 81, 0.3) + col * 0.37) % 1.4
        d = ph - y
        v = (1 - d * 2.5) if 0 <= d < 0.4 else 0
        return _scale(rgb, 0.1 + v, col / 16)
    if mode == "meteor":
        pos = (t * 0.5) % 1.6 - 0.3
        d = (x + y * 0.3) - pos
        v = (1 - d / 0.3) if 0 <= d < 0.3 else 0
        return _scale(rgb, 0.08 + v, x)
    if mode in ("music3", "music2"):
        col = round(k.x / 35)
        h = 0.5 + 0.45 * math.sin(t * 5 + col * 1.3) * math.sin(t * 2.3 + col * 0.7)
        on = (1 - y) < h + 0.15
        return _hue(col / 16 * 0.8 + (0 if mode == "music3" else 0.5)) if on else _scale(0x202020, 0.6, 0)
    if mode == "screen":
        return _hue(0.55 + 0.1 * math.sin(t * 0.8), 0.9)
    return _scale(rgb, 1, x)


def paint_preview(p: QPainter, rect: QRectF, mode: str, t: float, rgb: int | None, speed: int = 2,
                  option: str | None = None, brightness: int = 4, radius: float = 7) -> None:
    th = theme()
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(th.c("preview-bg"))
    p.drawRoundedRect(rect, radius, radius)
    pad = rect.height() * 0.1
    inner = rect.adjusted(pad * 1.6, pad, -pad * 1.6, -pad)
    s = min(inner.width() / CANVAS_W, inner.height() / CANVAS_H)
    ox = inner.left() + (inner.width() - CANVAS_W * s) / 2
    oy = inner.top() + (inner.height() - CANVAS_H * s) / 2
    off = th.c("preview-off")
    bf = 0.35 + 0.65 * brightness / 4
    for k in KEYS:
        r = QRectF(ox + k.x * s + 1.5 * s, oy + k.y * s + 1.5 * s, (k.w + 4) * s, 28 * s)
        c = key_color(mode, k, t, rgb, speed, option)
        if c is None:
            c = off
        else:
            c = QColor(round(c.red() * bf), round(c.green() * bf), round(c.blue() * bf))
            if c.red() + c.green() + c.blue() < 60:
                c = off
        p.setBrush(c)
        p.drawRoundedRect(r, 2.4 * s, 2.4 * s)
    p.restore()


def paint_strip(p: QPainter, rect: QRectF, mode: str, t: float, rgb: int | None, speed: int = 2,
                option: str | None = None, brightness: int = 4, radius: float = 7) -> None:
    """Tira lateral: una fila de LED sobre la silueta del teclado."""
    th = theme()
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(th.c("preview-bg"))
    p.drawRoundedRect(rect, radius, radius)
    pad = rect.height() * 0.12
    inner = rect.adjusted(pad * 1.6, pad, -pad * 1.6, -pad)
    s = min(inner.width() / CANVAS_W, inner.height() / CANVAS_H)
    ox = inner.left() + (inner.width() - CANVAS_W * s) / 2
    oy = inner.top() + (inner.height() - CANVAS_H * s) / 2
    off = th.c("preview-off")
    p.setBrush(off)
    for k in KEYS:
        p.drawRoundedRect(QRectF(ox + k.x * s + 1.5 * s, oy + k.y * s + 1.5 * s, (k.w + 4) * s, 28 * s), 2 * s, 2 * s)
    n = 24
    bf = 0.35 + 0.65 * brightness / 4
    seg_w = CANVAS_W * s / n
    y = oy + CANVAS_H * s + pad * 0.15

    class _K:  # tecla ficticia para reutilizar key_color
        pass
    for i in range(n):
        fk = _K()
        fk.x, fk.w, fk.y, fk.slot = i * CANVAS_W / n, CANVAS_W / n - 7, 0, i
        _SEEDS.setdefault(i, (i * 0.61803) % 1)
        mode_ = mode if mode in ("off", "static", "breath", "neon", "wave", "snake") else "static"
        if mode_ == "snake":
            head = (t * (0.35 + speed * 0.3) * 10) % n
            if option == "return":
                cyc = (t * (0.35 + speed * 0.3) * 10) % (2 * n)
                head = cyc if cyc < n else 2 * n - cyc
            d = abs(head - i)
            c = _scale(rgb, 1 - d / 5, i / n) if d < 5 else None
        else:
            c = key_color(mode_, fk, t, rgb, speed, option)
        if c is None:
            c = off
        else:
            c = QColor(round(c.red() * bf), round(c.green() * bf), round(c.blue() * bf))
        p.setBrush(c)
        p.drawRoundedRect(QRectF(ox + i * seg_w + 1, y, seg_w - 2, max(3.0, pad * 0.55)), 1.5, 1.5)
    p.restore()
