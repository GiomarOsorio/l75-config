"""Teclado L75 dibujado con QPainter, con los estados del diseño.

Medidas en unidades del driver (LAYOUT de l75_data). Escala s = ancho / 579.
  rect de la tecla: (x, y, w + 7, 32)          falda: radio 4,6 u, key-skirt
  cara: inset 3 · 1,6 · 3 · 5 u, radio 3,4 u   leyenda: Inter 500, 8,4 / 7 / 6,2 u
  nombre original (reasignada): 5,6 u arriba a la izquierda
  seleccionada: anillo de 2 px de acento + halo de 4 px
  pintada: cara = color, falda = color oscurecido 45 %, halo 9 u
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QFontMetricsF, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from ..keymap import KEYS, PhysicalKey
from .theme import font, paint_rgb_line, theme

CANVAS_W, CANVAS_H = 579.0, 225.0


@dataclass
class KeyLabel:
    legend: str = ""
    sub: str = ""          # nombre original pequeño (reasignada)
    cls: str = ""          # "" | remap | off | dim | held
    icon: str | None = None
    tip: str = ""


def mix(c: QColor, other: QColor, f: float) -> QColor:
    return QColor(round(c.red() + (other.red() - c.red()) * f), round(c.green() + (other.green() - c.green()) * f),
                  round(c.blue() + (other.blue() - c.blue()) * f))


def luminance(c: QColor) -> float:
    def ch(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    return 0.2126 * ch(c.red()) + 0.7152 * ch(c.green()) + 0.0722 * ch(c.blue())


class KeyboardView(QWidget):
    keyClicked = Signal(object)
    keyPainted = Signal(object)
    lockedClicked = Signal(object)
    strokeStarted = Signal()

    def __init__(self, mode: str = "remap", deck: bool = True, parent=None):
        super().__init__(parent)
        self.mode = mode            # remap | paint | outline | scan
        self.deck = deck
        self.labels: dict[int, KeyLabel] = {}
        self.colors: dict[int, int] = {}
        self.selected: int | None = None
        self.hover: int | None = None
        self.locked: set[int] = set()
        self.picking = False
        self.pad = (18, 18, 18, 22) if deck else (4, 4, 4, 4)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.setMinimumSize(520, 210)
        self._painting = False
        self._last_painted: int | None = None
        self._t0 = time.monotonic()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.update)
        if mode == "scan":
            self._timer.start(33)
        theme().changed.connect(self.update)

    # ------------------------------------------------------------ geometría
    def hasHeightForWidth(self):  # noqa: N802
        return True

    def heightForWidth(self, w):  # noqa: N802
        l, t, r, b = self.pad
        return round((w - l - r) * CANVAS_H / CANVAS_W) + t + b

    def sizeHint(self):
        from PySide6.QtCore import QSize
        return QSize(900, self.heightForWidth(900))

    def _geom(self):
        l, t, r, b = self.pad
        aw, ah = self.width() - l - r, self.height() - t - b
        s = min(aw / CANVAS_W, ah / CANVAS_H)
        ox = l + (aw - CANVAS_W * s) / 2
        oy = t + (ah - CANVAS_H * s) / 2
        return s, ox, oy

    def key_rect(self, k: PhysicalKey) -> QRectF:
        s, ox, oy = self._geom()
        return QRectF(ox + k.x * s, oy + k.y * s, (k.w + 7) * s, 32 * s)

    def key_at(self, pos) -> PhysicalKey | None:
        for k in KEYS:
            if self.key_rect(k).contains(pos):
                return k
        return None

    # ------------------------------------------------------------ pintura
    def paintEvent(self, _e):
        t = theme()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        if not self.isEnabled():
            p.setOpacity(0.4)
        if self.deck:
            r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
            p.setPen(QPen(t.c("deck-edge"), 1))
            p.setBrush(t.c("deck"))
            p.drawRoundedRect(r, 16, 16)
            w = r.width()
            paint_rgb_line(p, QRectF(r.left() + w * 0.24, r.bottom() - 1.5, w * 0.52, 2), 0.75)
        s, _ox, _oy = self._geom()
        now = time.monotonic() - self._t0
        if self.mode == "paint":
            # primero los halos, para que no tapen las teclas vecinas
            for k in KEYS:
                c = self.colors.get(k.slot)
                if c:
                    self._glow(p, self.key_rect(k), s, QColor((c >> 16) & 255, (c >> 8) & 255, c & 255))
        for k in KEYS:
            self._key(p, k, self.key_rect(k), s, now)
        p.end()

    def _glow(self, p: QPainter, r: QRectF, s: float, c: QColor):
        p.setPen(Qt.NoPen)
        steps = 5
        for i in range(steps, 0, -1):
            e = 9 * s * i / steps
            cc = QColor(c)
            cc.setAlphaF(0.38 * 0.32 * (1 - (i - 1) / steps))
            p.setBrush(cc)
            p.drawRoundedRect(r.adjusted(-e * 0.6, -e * 0.6, e * 0.6, e * 0.6), 4.6 * s + e * 0.6, 4.6 * s + e * 0.6)

    def _key(self, p: QPainter, k: PhysicalKey, r: QRectF, s: float, now: float):
        t = theme()
        lab = self.labels.get(k.slot)
        cls = lab.cls if lab else ""
        hover = self.hover == k.slot and self.mode in ("remap", "paint") and k.slot not in self.locked
        sel = self.selected == k.slot
        rr = 4.6 * s
        face_r = QRectF(r.left() + 3 * s, r.top() + 1.6 * s, r.width() - 6 * s, r.height() - 6.6 * s)

        if self.mode in ("outline", "scan"):
            edge = t.c("border-strong")
            fill = QColor(0, 0, 0, 0)
            if self.mode == "scan":
                ph = (now / 1.8 - (k.x / 572) * 1.2 / 1.8) % 1.0
                a = max(0.0, 1 - abs(ph - 0.4) / 0.4) if ph < 0.8 else 0.0
                acc_line = t.c("accent-line")
                edge = mix(edge, QColor(acc_line.red(), acc_line.green(), acc_line.blue()), a * 0.7)
                fill = t.c("accent-soft")
                fill.setAlphaF(fill.alphaF() * a)
            p.setPen(QPen(edge, 1))
            p.setBrush(fill)
            p.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), rr, rr)
            return

        # --- colores según estado
        legend_col = t.c("key-legend")
        weight = 500
        painted = None
        if self.mode == "paint":
            c = self.colors.get(k.slot)
            if c:
                painted = QColor((c >> 16) & 255, (c >> 8) & 255, c & 255)
            else:
                cls = "dim"
        if painted is not None:
            skirt = mix(painted, QColor("black"), 0.45)
            edge = mix(painted, QColor("black"), 0.62)
            top = QLinearGradient(face_r.topLeft(), face_r.bottomLeft())
            top.setColorAt(0, mix(painted, QColor("white"), 0.16))
            top.setColorAt(1, painted)
            face = QBrush(top)
            legend_col = QColor("#0B0D10") if luminance(painted) > 0.35 else QColor("#FFFFFF")
        else:
            skirt = t.c("key-skirt")
            edge = t.c("key-edge")
            g = QLinearGradient(face_r.topLeft(), face_r.bottomLeft())
            if cls in ("remap", "held"):
                edge = t.c("key-remap-edge") if cls == "remap" else t.c("accent")
                g.setColorAt(0, t.c("key-remap-1" if cls == "remap" else "key-remap-2"))
                g.setColorAt(1, t.c("key-remap-2" if cls == "remap" else "key-remap-1"))
                legend_col = t.c("accent")
                weight = 600
            elif cls == "locked":  # tecla del sistema: no se puede cambiar (rojo, como el driver)
                err = t.c("error")
                f = 0.16 if t.dark else 0.10
                g.setColorAt(0, mix(t.c("key-top-1"), err, f))
                g.setColorAt(1, mix(t.c("key-top-2"), err, f))
                skirt = mix(skirt, err, f)
                edge = mix(t.c("key-edge"), err, 0.6)
                legend_col = err
                weight = 600
            elif cls == "dim":
                g.setColorAt(0, t.c("key-off-top"))
                g.setColorAt(1, t.c("key-off-top"))
                legend_col = t.c("text-3")
            elif cls == "off":
                legend_col = t.c("text-3")
            else:
                g.setColorAt(0, t.c("key-hover-top") if hover else t.c("key-top-1"))
                g.setColorAt(1, t.c("key-top-2"))
            if hover and cls not in ("remap", "held"):
                edge = t.c("key-hover-edge")
            face = QBrush(g)
            if cls == "off":
                face = None

        # --- selección: halo de 4 px + anillo de 2 px
        if sel:
            p.setPen(Qt.NoPen)
            p.setBrush(t.c("accent-soft"))
            p.drawRoundedRect(r.adjusted(-6, -6, 6, 6), rr + 6, rr + 6)
            p.setBrush(t.c("accent"))
            p.drawRoundedRect(r.adjusted(-2, -2, 2, 2), rr + 2, rr + 2)
            edge = t.c("accent")

        # --- falda
        p.setPen(QPen(edge, 1))
        p.setBrush(skirt)
        p.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), rr, rr)

        # --- cara
        if cls == "held":
            face_r = QRectF(r.left() + 3 * s, r.top() + 3 * s, r.width() - 6 * s, r.height() - 6.4 * s)
        p.setPen(Qt.NoPen)
        if face is None:  # desactivada: trama a 135°
            p.setBrush(t.c("key-off-top"))
            p.drawRoundedRect(face_r, 3.4 * s, 3.4 * s)
            path = QPainterPath()
            path.addRoundedRect(face_r, 3.4 * s, 3.4 * s)
            p.save()
            p.setClipPath(path)
            pen = QPen(t.c("key-off-hatch"), 1.5 * s)
            p.setPen(pen)
            step = 4.5 * s
            x = face_r.left() - face_r.height()
            while x < face_r.right():
                p.drawLine(QPointF(x, face_r.bottom()), QPointF(x + face_r.height(), face_r.top()))
                x += step
            p.restore()
        else:
            p.setBrush(face)
            p.drawRoundedRect(face_r, 3.4 * s, 3.4 * s)

        # --- leyenda
        text = lab.legend if (lab and lab.legend is not None and (lab.legend or lab.icon)) else k.name
        sub = lab.sub if lab else ""
        icon = lab.icon if lab else None
        inner = face_r.adjusted(1.5 * s, 0, -1.5 * s, 0)
        if sub:
            p.setFont(font(5.6 * s, 500))
            p.setPen(t.c("key-sub") if painted is None else legend_col)
            p.drawText(QRectF(r.left() + 2.6 * s, r.top() + 2 * s, r.width() - 4 * s, 7 * s),
                       Qt.AlignLeft | Qt.AlignTop, sub)
            inner = QRectF(inner.left(), face_r.top() + face_r.height() * 0.38, inner.width(),
                           face_r.height() * 0.62 - 2.6 * s + 2.6 * s)
        if icon:
            sz = 10 * s
            pm = t.pixmap(icon, legend_col.name(), max(8, round(sz)))
            p.drawPixmap(QRectF(inner.center().x() - sz / 2, inner.center().y() - sz / 2, sz, sz), pm,
                         QRectF(pm.rect()))
            return
        if not text:
            return
        sizes = (8.4, 7.0, 6.2, 5.4, 4.8)
        lines = text.split("\n")
        f = None
        for sz in sizes:
            f = font(sz * s, weight)
            fm = QFontMetricsF(f)
            if max(fm.horizontalAdvance(ln) for ln in lines) <= inner.width() and fm.height() * len(lines) <= inner.height() + 2:
                break
        p.setFont(f)
        p.setPen(legend_col)
        p.drawText(inner, Qt.AlignCenter, text)

    # ------------------------------------------------------------ ratón
    def mouseMoveEvent(self, e):
        k = self.key_at(e.position())
        slot = k.slot if k else None
        if slot != self.hover:
            self.hover = slot
            self.update()
            if k:
                lab = self.labels.get(k.slot)
                if self.mode == "paint":
                    c = self.colors.get(k.slot, 0)
                    self.setToolTip(f"{k.name} · " + (f"#{c:06X}" if c else "apagada"))
                else:
                    self.setToolTip(lab.tip if lab and lab.tip else k.name)
            else:
                self.setToolTip("")
        if self.mode == "paint":
            self.setCursor(Qt.CrossCursor if not self.picking else Qt.PointingHandCursor)
            if self._painting and k and k.slot != self._last_painted:
                self._last_painted = k.slot
                self.keyPainted.emit(k)
        elif self.mode == "remap":
            self.setCursor(Qt.ForbiddenCursor if k and k.slot in self.locked else
                           (Qt.PointingHandCursor if k else Qt.ArrowCursor))

    def leaveEvent(self, e):
        self.hover = None
        self.update()

    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton or self.mode not in ("remap", "paint"):
            return
        k = self.key_at(e.position())
        if k and k.slot in self.locked:
            self.lockedClicked.emit(k)
            return
        if not k:
            return
        if self.mode == "paint":
            self._painting = not self.picking
            self._last_painted = k.slot
            self.strokeStarted.emit()
            self.keyPainted.emit(k)
        else:
            self.selected = k.slot
            self.update()
            self.keyClicked.emit(k)

    def mouseReleaseEvent(self, e):
        self._painting = False
        self._last_painted = None

