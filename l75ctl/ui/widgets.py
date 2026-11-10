"""Componentes del sistema de diseño (botones, interruptor, slider con marcas,
campo numérico, segmentos, tarjetas, toasts, diálogos y selector de color)."""

from __future__ import annotations

import weakref

from PySide6.QtCore import (Property, QEasingCurve, QEvent, QPoint, QPointF, QPropertyAnimation, QRectF, QSize, Qt,
                            QTimer, Signal)
from PySide6.QtGui import QColor, QIntValidator, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QAbstractButton, QButtonGroup, QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QSizePolicy, QSlider, QToolButton, QVBoxLayout, QWidget)

from ..i18n import t as tr
from .theme import font, rgb_gradient, theme

# ---------------------------------------------------------------- utilidades


def repolish(w: QWidget) -> None:
    w.style().unpolish(w)
    w.style().polish(w)
    w.update()


def set_prop(w: QWidget, name: str, value) -> None:
    if w.property(name) != value:
        w.setProperty(name, value)
        repolish(w)


def hbox(*items, spacing: int = 8, margins=(0, 0, 0, 0), parent: QWidget | None = None) -> QHBoxLayout:
    lay = QHBoxLayout(parent) if parent is not None else QHBoxLayout()
    lay.setSpacing(spacing)
    lay.setContentsMargins(*margins)
    for it in items:
        _add(lay, it)
    return lay


def vbox(*items, spacing: int = 8, margins=(0, 0, 0, 0), parent: QWidget | None = None) -> QVBoxLayout:
    lay = QVBoxLayout(parent) if parent is not None else QVBoxLayout()
    lay.setSpacing(spacing)
    lay.setContentsMargins(*margins)
    for it in items:
        _add(lay, it)
    return lay


def _add(lay, it):
    if it is None:
        return
    if it == "stretch":
        lay.addStretch(1)
    elif isinstance(it, int):
        lay.addSpacing(it)
    elif isinstance(it, QWidget):
        lay.addWidget(it)
    else:
        lay.addLayout(it)


def label(text: str = "", role: str | None = None, wrap: bool = False, tone: str | None = None,
          rich: bool = False) -> QLabel:
    lb = QLabel(text)
    if role:
        lb.setProperty("role", role)
    if tone:
        lb.setProperty("tone", tone)
    if wrap:
        lb.setWordWrap(True)
    lb.setTextFormat(Qt.RichText if rich else Qt.PlainText)
    if rich:
        lb.setOpenExternalLinks(False)
    return lb


def pill(text: str, kind: str = "neutral") -> QLabel:
    lb = QLabel(text)
    lb.setProperty("pill", kind)
    lb.setFixedHeight(22)
    return lb


def kbd(text: str) -> QLabel:
    lb = QLabel(text)
    lb.setProperty("role", "kbd")
    lb.setAlignment(Qt.AlignCenter)
    return lb


def divider(kind: str = "h") -> QFrame:
    f = QFrame()
    f.setProperty("divider", kind)
    return f


def card(kind: str = "true", padding=(20, 18, 20, 18), spacing: int = 12) -> tuple[QFrame, QVBoxLayout]:
    f = QFrame()
    f.setProperty("card", kind)
    lay = vbox(spacing=spacing, margins=padding, parent=f)
    return f, lay


# ---------------------------------------------------------------- iconos que siguen al tema

_ICON_USERS: "weakref.WeakKeyDictionary[QWidget, tuple]" = weakref.WeakKeyDictionary()


def _variant_color(btn) -> str:
    v = btn.property("variant")
    return {"primary": "on-accent", "danger": "error", "danger-solid": "on-error", "ghost": "text-2",
            "rec-on": "error", "link": "accent"}.get(v, "text-1")


def set_icon(w, name: str | None, color: str | None = None, size: int = 16, active: str | None = None) -> None:
    """Pone un icono SVG del diseño; se vuelve a pintar al cambiar de tema."""
    if not name:
        w.setIcon(theme().icon("cerrar", "#00000000", size))
        _ICON_USERS.pop(w, None)
        return
    _ICON_USERS[w] = (name, color, size, active)
    _apply_icon(w)


def _apply_icon(w):
    name, color, size, active = _ICON_USERS[w]
    col = color or (_variant_color(w) if isinstance(w, QPushButton) else "text-2")
    if isinstance(w, QLabel):
        w.setPixmap(theme().pixmap(name, col, size))
    else:
        w.setIcon(theme().icon(name, col, size, active))
        w.setIconSize(QSize(size, size))


def _refresh_icons():
    for w in list(_ICON_USERS.keys()):
        try:
            _apply_icon(w)
        except RuntimeError:
            pass


def icon_label(name: str, color: str = "text-2", size: int = 16) -> QLabel:
    lb = QLabel()
    lb.setFixedSize(size, size)
    set_icon(lb, name, color, size)
    return lb


def button(text: str = "", variant: str = "secondary", icon: str | None = None, size: str | None = None,
           tip: str | None = None, on_click=None) -> QPushButton:
    b = QPushButton(text)
    b.setProperty("variant", variant)
    if size:
        b.setProperty("size", size)
    if not text:
        b.setProperty("icononly", True)
    b.setCursor(Qt.PointingHandCursor)
    if icon:
        set_icon(b, icon, size=14 if size == "sm" else 16)
    if tip:
        b.setToolTip(tip)
    if on_click:
        b.clicked.connect(on_click)
    return b


def set_variant(b: QPushButton, variant: str) -> None:
    set_prop(b, "variant", variant)
    if b in _ICON_USERS:
        _apply_icon(b)


def disable_with_reason(w: QWidget, reason: str | None) -> None:
    """Deshabilitado, siempre con motivo (tooltip)."""
    w.setEnabled(reason is None)
    w.setToolTip(reason or w.property("baseTip") or "")


# ---------------------------------------------------------------- interruptor


class Switch(QAbstractButton):
    """Interruptor 36 × 20 con mando de 16 px (token track/knob/accent)."""

    def __init__(self, checked: bool = False, rgb: bool = False, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.rgb = rgb
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(36, 20)
        self._pos = 1.0 if checked else 0.0
        self._anim = QPropertyAnimation(self, b"pos", self)
        self._anim.setDuration(180)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self.toggled.connect(self._animate)
        self.setFocusPolicy(Qt.TabFocus)

    def _animate(self, on):
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def _get_pos(self):
        return self._pos

    def _set_pos(self, v):
        self._pos = v
        self.update()

    pos = Property(float, _get_pos, _set_pos)

    def setChecked(self, on: bool) -> None:  # noqa: N802 - sin animación al cargar
        super().setChecked(on)
        self._pos = 1.0 if on else 0.0
        self.update()

    def sizeHint(self):
        return QSize(36, 20)

    def paintEvent(self, _e):
        t = theme()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if not self.isEnabled():
            p.setOpacity(0.4)
        r = QRectF(0, 0, 36, 20)
        hover = self.underMouse() and self.isEnabled()
        if self.isChecked():
            brush = rgb_gradient(0, 36) if self.rgb else t.c("accent-hover" if hover else "accent")
        else:
            brush = t.c("track-hover" if hover else "track")
        p.setPen(Qt.NoPen)
        p.setBrush(brush)
        p.drawRoundedRect(r, 10, 10)
        if self.hasFocus():
            p.setPen(QPen(t.c("focus"), 2))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(r.adjusted(1, 1, -1, -1), 9, 9)
        x = 2 + 16 * self._pos
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 70))
        p.drawEllipse(QRectF(x, 3, 16, 16))
        p.setBrush(t.c("knob"))
        p.drawEllipse(QRectF(x, 2, 16, 16))

    def enterEvent(self, e):
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.update()
        super().leaveEvent(e)


# ---------------------------------------------------------------- slider


class TickSlider(QSlider):
    """Slider con pista de 4 px, relleno de acento, mando de 16 px y marcas.

    Con `ticks=True` dibuja un punto por valor y los números debajo (0–4)."""

    def __init__(self, lo: int = 0, hi: int = 4, ticks: bool = True, parent=None):
        super().__init__(Qt.Horizontal, parent)
        self.setRange(lo, hi)
        self.ticks = ticks
        self.setFixedHeight(40 if ticks else 24)
        self.setCursor(Qt.PointingHandCursor)
        self.setMouseTracking(True)
        self.setPageStep(1)

    def _x(self, v: float) -> float:
        lo, hi = self.minimum(), self.maximum()
        return 8 + (self.width() - 16) * ((v - lo) / (hi - lo) if hi > lo else 0)

    def _value_at(self, x: float) -> int:
        lo, hi = self.minimum(), self.maximum()
        f = min(1.0, max(0.0, (x - 8) / max(1, self.width() - 16)))
        return round(lo + f * (hi - lo))

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and self.isEnabled():
            self.setSliderDown(True)
            self.setValue(self._value_at(e.position().x()))
            e.accept()

    def mouseMoveEvent(self, e):
        if self.isSliderDown():
            self.setValue(self._value_at(e.position().x()))
        self.update()

    def mouseReleaseEvent(self, e):
        if self.isSliderDown():
            self.setSliderDown(False)
            self.sliderReleased.emit()

    def leaveEvent(self, e):
        self.update()

    def paintEvent(self, _e):
        t = theme()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if not self.isEnabled():
            p.setOpacity(0.4)
        y = 12
        x0, x1 = 8, self.width() - 8
        xv = self._x(self.value())
        p.setPen(Qt.NoPen)
        p.setBrush(t.c("track"))
        p.drawRoundedRect(QRectF(x0, y - 2, x1 - x0, 4), 2, 2)
        p.setBrush(t.c("accent"))
        p.drawRoundedRect(QRectF(x0, y - 2, xv - x0, 4), 2, 2)
        if self.ticks:
            for v in range(self.minimum(), self.maximum() + 1):
                xx = self._x(v)
                on = v <= self.value()
                c = t.c("on-accent") if on else t.c("text-3")
                if on:
                    c.setAlphaF(0.55)
                p.setBrush(c)
                p.drawEllipse(QPointF(xx, y), 2, 2)
            p.setFont(font(11, 500, mono=True))
            for v in range(self.minimum(), self.maximum() + 1):
                xx = self._x(v)
                p.setPen(t.c("text-1") if v == self.value() else t.c("text-3"))
                p.drawText(QRectF(xx - 10, 26, 20, 14), Qt.AlignCenter, str(v))
            p.setPen(Qt.NoPen)
        hover = self.underMouse() or self.isSliderDown()
        if self.hasFocus():
            p.setBrush(t.c("focus"))
            p.drawEllipse(QPointF(xv, y), 10, 10)
        elif hover and self.isEnabled():
            p.setBrush(t.c("accent-soft"))
            p.drawEllipse(QPointF(xv, y), 13, 13)
        p.setBrush(QColor(0, 0, 0, 90))
        p.drawEllipse(QPointF(xv, y + 1), 8, 8)
        p.setBrush(t.c("knob"))
        p.drawEllipse(QPointF(xv, y), 8, 8)


# ---------------------------------------------------------------- campo numérico


class Stepper(QFrame):
    """Campo numérico «− valor unidad +» (token .num)."""

    valueChanged = Signal(int)

    def __init__(self, lo: int, hi: int, value: int = 0, unit: str = "", step: int = 1, width: int = 46,
                 buttons: bool = True, parent=None):
        super().__init__(parent)
        self.setProperty("num", True)
        self.lo, self.hi, self.step = lo, hi, step
        self._value = value
        lay = hbox(spacing=0, parent=self)
        self.minus = QToolButton()
        self.plus = QToolButton()
        set_icon(self.minus, "menos", "text-2", 14)
        set_icon(self.plus, "mas", "text-2", 14)
        self.edit = QLineEdit(str(value))
        self.edit.setAlignment(Qt.AlignCenter)
        self.edit.setFixedWidth(width)
        self.edit.setValidator(QIntValidator(-99999, 99999, self))
        self.unit = QLabel(unit)
        if buttons:
            lay.addWidget(self.minus)
        else:
            self.minus.hide()
            lay.addSpacing(4)
        lay.addWidget(self.edit)
        if unit:
            lay.addWidget(self.unit)
        if buttons:
            lay.addWidget(self.plus)
        else:
            self.plus.hide()
        self.setFixedHeight(32)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.minus.clicked.connect(lambda: self.setValue(self._value - self.step))
        self.plus.clicked.connect(lambda: self.setValue(self._value + self.step))
        self.edit.editingFinished.connect(self._edited)
        self.edit.installEventFilter(self)
        self._sync()

    def eventFilter(self, obj, ev):
        if obj is self.edit:
            if ev.type() == QEvent.FocusIn:
                set_prop(self, "focus", True)
            elif ev.type() == QEvent.FocusOut:
                set_prop(self, "focus", False)
            elif ev.type() == QEvent.Wheel and self.edit.hasFocus():
                self.setValue(self._value + (self.step if ev.angleDelta().y() > 0 else -self.step))
                return True
            elif ev.type() == QEvent.KeyPress and ev.key() in (Qt.Key_Up, Qt.Key_Down):
                self.setValue(self._value + (self.step if ev.key() == Qt.Key_Up else -self.step))
                return True
        return super().eventFilter(obj, ev)

    def _edited(self):
        try:
            self.setValue(int(self.edit.text()))
        except ValueError:
            self._sync()

    def value(self) -> int:
        return self._value

    def setValue(self, v: int, emit: bool = True) -> None:  # noqa: N802
        v = max(self.lo, min(self.hi, int(v)))
        changed = v != self._value
        self._value = v
        self._sync()
        if changed and emit:
            self.valueChanged.emit(v)

    def setRange(self, lo, hi):  # noqa: N802
        self.lo, self.hi = lo, hi
        self.setValue(self._value)

    def _sync(self):
        self.edit.setText(str(self._value))
        self.minus.setEnabled(self._value > self.lo)
        self.plus.setEnabled(self._value < self.hi)


# ---------------------------------------------------------------- control segmentado


class Segmented(QFrame):
    """Grupo exclusivo de QToolButton dentro de un marco (.seg)."""

    changed = Signal(object)

    def __init__(self, items=(), block: bool = False, mono: bool = False, kind: str = "true", parent=None):
        super().__init__(parent)
        self.setProperty("seg", kind)
        self.block = block
        self.mono = mono
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.lay = hbox(spacing=2, margins=(2, 2, 2, 2) if kind == "true" else (3, 3, 3, 3), parent=self)
        self.buttons: list[QToolButton] = []
        self.data: list = []
        for it in items:
            self.add(*it) if isinstance(it, tuple) else self.add(it, it)
        self.group.idClicked.connect(lambda i: self.changed.emit(self.data[i]))
        if not block:
            self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)

    def add(self, text: str, data=None, icon: str | None = None, tip: str | None = None) -> QToolButton:
        b = QToolButton()
        b.setText(text)
        b.setCheckable(True)
        b.setCursor(Qt.PointingHandCursor)
        if self.mono:
            b.setProperty("mono", True)
        if icon:
            set_icon(b, icon, "text-2", 14, active="text-1")
            b.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        if tip:
            b.setToolTip(tip)
        if self.block:
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        i = len(self.buttons)
        self.group.addButton(b, i)
        self.buttons.append(b)
        self.data.append(text if data is None else data)
        self.lay.addWidget(b)
        if i == 0:
            b.setChecked(True)
        return b

    def value(self):
        i = self.group.checkedId()
        return self.data[i] if i >= 0 else None

    def index(self) -> int:
        return self.group.checkedId()

    def setValue(self, data) -> None:  # noqa: N802
        if data in self.data:
            self.buttons[self.data.index(data)].setChecked(True)

    def setIndex(self, i: int) -> None:  # noqa: N802
        if 0 <= i < len(self.buttons):
            self.buttons[i].setChecked(True)

    def button_for(self, data) -> QToolButton | None:
        return self.buttons[self.data.index(data)] if data in self.data else None


# ---------------------------------------------------------------- spinner y batería


class Spinner(QWidget):
    def __init__(self, size: int = 14, color: str = "accent", parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.color = color
        self.angle = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)

    def showEvent(self, e):
        self.timer.start(16)

    def hideEvent(self, e):
        self.timer.stop()

    def _tick(self):
        self.angle = (self.angle + 7) % 360
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        pen = QPen(theme().c(self.color), 2)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        r = QRectF(1, 1, self.width() - 2, self.height() - 2)
        p.drawArc(r, -self.angle * 16, 270 * 16)


class Battery(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.level = 0
        self.charging = False
        self.setFixedSize(26, 14)

    def set(self, level: int, charging: bool):
        self.level, self.charging = level, charging
        self.update()

    def paintEvent(self, _e):
        t = theme()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(t.c("text-2"), 1.5))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(0.75, 1.25, 21, 11.5), 3, 3)
        p.setPen(Qt.NoPen)
        p.setBrush(t.c("text-2"))
        p.drawRoundedRect(QRectF(22.5, 4.5, 2, 5), 1, 1)
        col = t.c("success") if self.level > 20 else (t.c("warning") if self.level > 10 else t.c("error"))
        p.setBrush(col)
        p.drawRoundedRect(QRectF(2.75, 3.25, 17 * max(0, min(100, self.level)) / 100, 7.5), 1, 1)


# ---------------------------------------------------------------- barra de progreso RGB


class RgbProgress(QWidget):
    def __init__(self, height: int = 8, parent=None):
        super().__init__(parent)
        self.value = 0.0
        self.setFixedHeight(height)

    def set(self, f: float):
        self.value = max(0.0, min(1.0, f))
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        h = self.height()
        r = QRectF(0, 0, self.width(), h)
        p.setPen(Qt.NoPen)
        p.setBrush(theme().c("track"))
        p.drawRoundedRect(r, h / 2, h / 2)
        if self.value > 0:
            path = QPainterPath()
            path.addRoundedRect(r, h / 2, h / 2)
            p.setClipPath(path)
            p.setBrush(rgb_gradient(0, self.width()))
            p.drawRect(QRectF(0, 0, self.width() * self.value, h))


class Meter(QWidget):
    """Barra fina (4 px) con tono según el uso: capacidad de macro, cuadros…"""

    def __init__(self, width: int | None = None, parent=None):
        super().__init__(parent)
        self.value = 0.0
        self.tone = "accent"
        self.setFixedHeight(4)
        if width:
            self.setFixedWidth(width)

    def set(self, f: float, tone: str = "accent"):
        self.value, self.tone = max(0.0, min(1.0, f)), tone
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(theme().c("track"))
        p.drawRoundedRect(QRectF(0, 0, self.width(), 4), 2, 2)
        p.setBrush(theme().c(self.tone))
        p.drawRoundedRect(QRectF(0, 0, self.width() * self.value, 4), 2, 2)


# ---------------------------------------------------------------- aviso (banner)


class Banner(QFrame):
    ICONS = {"info": "info", "ok": "exito", "warn": "aviso", "err": "error"}
    COLORS = {"info": "accent", "ok": "success", "warn": "warning", "err": "error"}

    def __init__(self, kind: str = "info", text: str = "", action: str | None = None, on_action=None,
                 action_variant: str = "primary", parent=None):
        super().__init__(parent)
        self.setProperty("banner", "" if kind == "info" else kind)
        self.setMinimumHeight(48)
        self.icon = icon_label(self.ICONS[kind], self.COLORS[kind], 16)
        self.text = label(text, wrap=True, rich=True)
        self.action = None
        lay = hbox(self.icon, spacing=12, margins=(14, 8, 8, 8), parent=self)
        lay.addWidget(self.text, 1)
        if action:
            self.action = button(action, action_variant, size="sm", on_click=on_action)
            lay.addWidget(self.action)

    def set_text(self, text: str):
        self.text.setText(text)


# ---------------------------------------------------------------- encabezado de página


class PageHeader(QWidget):
    def __init__(self, title: str, subtitle: str = "", parent=None):
        super().__init__(parent)
        self.title = label(title, "display")
        self.subtitle = label(subtitle, "body2", wrap=True)
        left = vbox(self.title, self.subtitle, spacing=2)
        self.actions = hbox(spacing=8)
        lay = hbox(spacing=16, parent=self)
        lay.addLayout(left, 1)
        lay.addLayout(self.actions)
        lay.setAlignment(self.actions, Qt.AlignBottom)

    def add(self, w: QWidget):
        self.actions.addWidget(w)
        return w


# ---------------------------------------------------------------- toasts


class Toast(QFrame):
    ICONS = {"ok": ("exito", "success"), "err": ("error", "error"), "warn": ("aviso", "warning"),
             "info": ("info", "accent")}

    closed = Signal()

    def __init__(self, kind: str, text: str, action: str | None, on_action, parent):
        super().__init__(parent)
        self.setObjectName("Toast")
        self.setMinimumWidth(300)
        self.setMaximumWidth(480)
        self.setMinimumHeight(44)
        ic, col = self.ICONS.get(kind, self.ICONS["info"])
        lay = hbox(icon_label(ic, col, 16), spacing=10, margins=(14, 6, 6, 6), parent=self)
        tx = label(text, wrap=True)
        tx.setObjectName("ToastText")
        lay.addWidget(tx, 1)
        if action:
            def act():
                on_action()
                self.dismiss()
            lay.addWidget(button(action, "secondary", size="sm", on_click=act))
        lay.addWidget(button("", "ghost", "cerrar", size="sm", tip=tr("Close"), on_click=self.dismiss))
        theme().shadow(self, 2)
        if kind in ("ok", "info"):
            QTimer.singleShot(3200, self.dismiss)

    def dismiss(self):
        if not self.isVisible():
            return
        self.hide()
        self.closed.emit()
        self.deleteLater()


class Toaster(QWidget):
    """Capa sin fondo sobre el área de contenido: toasts abajo, centrados."""

    def __init__(self, host: QWidget):
        super().__init__(host)
        self.host = host
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.lay = vbox(spacing=8, parent=self)
        self.lay.setAlignment(Qt.AlignHCenter | Qt.AlignBottom)
        self.toasts: list[Toast] = []
        host.installEventFilter(self)
        self.hide()

    def eventFilter(self, obj, ev):
        if obj is self.host and ev.type() == QEvent.Resize:
            self._place()
        return False

    def _place(self):
        self.lay.activate()
        w = min(self.host.width() - 32, 520)
        h = self.lay.heightForWidth(w) if self.lay.hasHeightForWidth() else self.lay.sizeHint().height()
        h = max(h, self.lay.sizeHint().height())
        self.setGeometry((self.host.width() - w) // 2, self.host.height() - h - 24, w, h)

    def show_toast(self, kind: str, text: str, action: str | None = None, on_action=None):
        # sin duplicados ni más de 3 a la vez
        while len(self.toasts) >= 3:
            self.toasts[0].dismiss()
        t = Toast(kind, text, action, on_action, self)
        self.toasts.append(t)
        t.closed.connect(lambda t=t: self._closed(t))
        self.lay.addWidget(t, 0, Qt.AlignHCenter)
        self.show()
        self.raise_()
        self._place()
        eff = QGraphicsOpacityEffect(t)
        t.setGraphicsEffect(eff)
        an = QPropertyAnimation(eff, b"opacity", t)
        an.setDuration(180)
        an.setStartValue(0.0)
        an.setEndValue(1.0)
        an.setEasingCurve(QEasingCurve.OutCubic)
        an.finished.connect(lambda t=t: theme().shadow(t, 2) if t.isVisible() else None)
        an.start()

    def _closed(self, t):
        if t in self.toasts:
            self.toasts.remove(t)
        QTimer.singleShot(0, self._after_close)

    def _after_close(self):
        if not self.toasts:
            self.hide()
        else:
            self._place()


# ---------------------------------------------------------------- diálogo


class Dialog(QWidget):
    """Diálogo sin marco sobre un velo `scrim` (sin desenfoque)."""

    def __init__(self, window: QWidget, title: str, text: str, confirm: str, on_ok, danger: bool = False,
                 icon: str = "restaurar", require: str | None = None, cancel: str | None = None, extra=None):
        super().__init__(window)
        self.setObjectName("Scrim")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setGeometry(window.rect())
        self.on_ok = on_ok
        self.require = require
        box = QFrame(self)
        box.setObjectName("Dialog")
        box.setFixedWidth(448)
        self.box = box
        ic = QFrame()
        ic.setProperty("iconbox", "err" if danger else "neutral")
        ic.setFixedSize(36, 36)
        hbox(icon_label(icon, "error" if danger else "text-2", 18), margins=(9, 9, 9, 9), parent=ic)
        tt = label(title, "title", wrap=True)
        tx = label(text, "body2", wrap=True, rich=True)
        head = hbox(ic, spacing=12)
        head.setAlignment(ic, Qt.AlignTop)
        head.addLayout(vbox(tt, tx, spacing=4), 1)
        lay = vbox(spacing=14, margins=(20, 20, 20, 20), parent=box)
        lay.addLayout(head)
        if extra is not None:
            lay.addWidget(extra)
        self.field = None
        if require:
            word = f"<span style='color:{theme().hex('error')};font-weight:600'>{require}</span>"
            lab = label(tr("Type {word} to confirm").format(word=word), "strong", rich=True)
            self.field = QLineEdit()
            self.field.setProperty("mono", True)
            self.field.textChanged.connect(self._check)
            lay.addLayout(vbox(lab, self.field, spacing=6))
        self.ok = button(confirm, "danger-solid" if danger else "primary", on_click=self._accept)
        foot = hbox("stretch", button(cancel or tr("Cancel"), "ghost", on_click=self.close_dialog), self.ok, spacing=8)
        lay.addLayout(foot)
        theme().shadow(box, 2)
        self._check()
        window.installEventFilter(self)
        self.show()
        self.raise_()
        self._center()
        (self.field or self.ok).setFocus()

    def _check(self):
        if self.require:
            self.ok.setEnabled(self.field.text().strip() == self.require)

    def _center(self):
        self.box.adjustSize()
        self.box.move((self.width() - self.box.width()) // 2, (self.height() - self.box.height()) // 2)

    def eventFilter(self, obj, ev):
        if obj is self.parent() and ev.type() == QEvent.Resize:
            self.setGeometry(self.parent().rect())
            self._center()
        return False

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.close_dialog()
        elif e.key() in (Qt.Key_Return, Qt.Key_Enter) and self.ok.isEnabled():
            self._accept()
        else:
            super().keyPressEvent(e)

    def mousePressEvent(self, e):
        if not self.box.geometry().contains(e.position().toPoint()):
            self.close_dialog()

    def _accept(self):
        self.close_dialog()
        if self.on_ok:
            self.on_ok()

    def close_dialog(self):
        self.parent().removeEventFilter(self)
        self.hide()
        self.deleteLater()


# ---------------------------------------------------------------- color


def rgb_int(c: QColor) -> int:
    return (c.red() << 16) | (c.green() << 8) | c.blue()


def qcolor(rgb: int) -> QColor:
    return QColor((rgb >> 16) & 255, (rgb >> 8) & 255, rgb & 255)


KEY_SWATCHES = [0xFF0000, 0xFF8000, 0xFFFF00, 0x00FF00, 0x00FFFF, 0x0000FF, 0xFF00FF, 0xFFFFFF]
PAINT_SWATCHES = [0xFF3B3B, 0xFF8A1F, 0xFFB020, 0xFFE15A, 0x3DDC6B, 0x2BD2F0, 0x3D7BFF, 0x9B5CFF, 0xFF4DB8,
                  0xFFFFFF, 0x000000]


class Swatch(QAbstractButton):
    """Muestra de color 24 × 24 (normal / hover / elegida / no disponible)."""

    def __init__(self, rgb: int, size: int = 24, parent=None):
        super().__init__(parent)
        self.rgb = rgb
        self.setCheckable(True)
        self.setFixedSize(size + 8, size + 8)
        self.size_ = size
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(f"#{rgb:06X}" + (" · " + tr("key off") if rgb == 0 else ""))

    def paintEvent(self, _e):
        t = theme()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if not self.isEnabled():
            p.setOpacity(0.35)
        r = QRectF(4, 4, self.size_, self.size_)
        if self.isChecked():
            p.setPen(QPen(t.c("text-1"), 2))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(r.adjusted(-3, -3, 3, 3), 8, 8)
        elif self.underMouse() and self.isEnabled():
            p.setPen(QPen(t.c("border-strong"), 2))
            p.drawRoundedRect(r.adjusted(-2, -2, 2, 2), 7, 7)
        edge = QColor(255, 255, 255, 36) if t.dark else QColor(18, 22, 28, 40)
        p.setPen(QPen(edge, 1))
        p.setBrush(qcolor(self.rgb))
        p.drawRoundedRect(r, 6, 6)

    def enterEvent(self, e):
        self.update()

    def leaveEvent(self, e):
        self.update()


class SwatchRow(QWidget):
    picked = Signal(int)

    def __init__(self, colors, size: int = 24, extra: QWidget | None = None, parent=None):
        super().__init__(parent)
        self.group = QButtonGroup(self)
        self.group.setExclusive(False)
        self.swatches = []
        lay = hbox(spacing=0, parent=self)
        for c in colors:
            s = Swatch(c, size)
            s.clicked.connect(lambda _=False, c=c: self.picked.emit(c))
            self.swatches.append(s)
            lay.addWidget(s)
        if extra:
            lay.addSpacing(4)
            lay.addWidget(extra)
        lay.addStretch(1)

    def select(self, rgb: int | None):
        for s in self.swatches:
            s.setChecked(s.rgb == rgb)
            s.update()


class _SVField(QWidget):
    changed = Signal()

    def __init__(self, picker):
        super().__init__()
        self.picker = picker
        self.setFixedSize(220, 120)
        self.setCursor(Qt.CrossCursor)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect())
        path = QPainterPath()
        path.addRoundedRect(r, 6, 6)
        p.setClipPath(path)
        hue = QColor.fromHsvF(self.picker.h, 1, 1)
        g = QLinearGradient(0, 0, r.width(), 0)
        g.setColorAt(0, QColor("white"))
        g.setColorAt(1, hue)
        p.fillRect(r, g)
        g2 = QLinearGradient(0, 0, 0, r.height())
        g2.setColorAt(0, QColor(0, 0, 0, 0))
        g2.setColorAt(1, QColor(0, 0, 0, 255))
        p.fillRect(r, g2)
        p.setClipping(False)
        x, y = self.picker.s * r.width(), (1 - self.picker.v) * r.height()
        p.setPen(QPen(QColor("white"), 2))
        p.setBrush(self.picker.color())
        p.drawEllipse(QPointF(x, y), 6, 6)

    def _set(self, pos):
        self.picker.s = min(1, max(0, pos.x() / self.width()))
        self.picker.v = 1 - min(1, max(0, pos.y() / self.height()))
        self.picker.emit_change()

    def mousePressEvent(self, e):
        self._set(e.position())

    def mouseMoveEvent(self, e):
        if e.buttons() & Qt.LeftButton:
            self._set(e.position())


class _HueBar(QWidget):
    def __init__(self, picker):
        super().__init__()
        self.picker = picker
        self.setFixedSize(220, 14)
        self.setCursor(Qt.PointingHandCursor)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        g = QLinearGradient(0, 0, self.width(), 0)
        for i in range(7):
            g.setColorAt(i / 6, QColor.fromHsvF((i / 6) % 1.0, 1, 1))
        p.setPen(Qt.NoPen)
        p.setBrush(g)
        p.drawRoundedRect(QRectF(0, 3, self.width(), 8), 4, 4)
        x = self.picker.h * self.width()
        p.setPen(QPen(QColor("white"), 2))
        p.setBrush(QColor.fromHsvF(self.picker.h, 1, 1))
        p.drawEllipse(QPointF(min(self.width() - 6, max(6, x)), 7), 6, 6)

    def _set(self, pos):
        self.picker.h = min(0.999, max(0, pos.x() / self.width()))
        self.picker.emit_change()

    def mousePressEvent(self, e):
        self._set(e.position())

    def mouseMoveEvent(self, e):
        if e.buttons() & Qt.LeftButton:
            self._set(e.position())


class ColorPopover(QFrame):
    """Selector emergente: campo SV, barra de tono, HEX/R/G/B y colores del teclado."""

    colorChanged = Signal(int)

    def __init__(self, rgb: int, swatches=KEY_SWATCHES, parent=None):
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setObjectName("Popover")
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setAttribute(Qt.WA_StyledBackground, True)
        c = qcolor(rgb)
        self.h = max(0.0, c.hsvHueF())
        self.s, self.v = c.hsvSaturationF(), c.valueF()
        self.sv = _SVField(self)
        self.hue = _HueBar(self)
        self.hex = QLineEdit()
        self.hex.setProperty("mono", True)
        self.hex.setFixedWidth(84)
        self.rgbf = []
        for _ in range(3):
            e = QLineEdit()
            e.setProperty("mono", True)
            e.setFixedWidth(40)
            e.setValidator(QIntValidator(0, 255, e))
            e.editingFinished.connect(self._rgb_edited)
            self.rgbf.append(e)
        self.hex.editingFinished.connect(self._hex_edited)
        heads = hbox(label("HEX", "label"), 56, label("R", "label"), 28, label("G", "label"), 28,
                     label("B", "label"), "stretch", spacing=0)
        fields = hbox(self.hex, *self.rgbf, spacing=6)
        self.row = SwatchRow(swatches, 20)
        self.row.picked.connect(self.set_rgb_emit)
        lay = vbox(self.sv, self.hue, heads, fields, label(tr("Keyboard colours").upper(), "label"), self.row, spacing=8,
                   margins=(12, 12, 12, 12), parent=self)
        lay.setSpacing(8)
        self._sync_fields()

    def color(self) -> QColor:
        return QColor.fromHsvF(self.h, self.s, self.v)

    def emit_change(self):
        self.sv.update()
        self.hue.update()
        self._sync_fields()
        self.colorChanged.emit(rgb_int(self.color()))

    def set_rgb_emit(self, rgb: int):
        c = qcolor(rgb)
        self.h = max(0.0, c.hsvHueF()) if c.hsvHueF() >= 0 else self.h
        self.s, self.v = c.hsvSaturationF(), c.valueF()
        self.emit_change()
        self.hex.setText(f"#{rgb:06X}")

    def _sync_fields(self):
        c = self.color()
        self.hex.setText(c.name().upper())
        for e, v in zip(self.rgbf, (c.red(), c.green(), c.blue())):
            e.setText(str(v))
        self.row.select(rgb_int(c))

    def _hex_edited(self):
        t = self.hex.text().strip().lstrip("#")
        try:
            self.set_rgb_emit(int(t, 16) & 0xFFFFFF)
            set_prop(self.hex, "error", False)
        except ValueError:
            set_prop(self.hex, "error", True)

    def _rgb_edited(self):
        try:
            r, g, b = (int(e.text() or 0) for e in self.rgbf)
        except ValueError:
            return
        self.set_rgb_emit((r << 16) | (g << 8) | b)

    def popup_at(self, w: QWidget):
        self.adjustSize()
        pos = w.mapToGlobal(QPoint(0, w.height() + 6))
        self.move(pos)
        self.show()


class ColorButton(QPushButton):
    """Botón del pincel: muestra 24 px + #HEX en mono + chevron."""

    colorChanged = Signal(int)

    def __init__(self, rgb: int = 0xFFFFFF, swatches=KEY_SWATCHES, parent=None):
        super().__init__(parent)
        self.rgb = rgb
        self.swatches = swatches
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(32)
        self.setMinimumWidth(120)
        self.setStyleSheet("QPushButton{background:transparent;border:none;padding:0;}")
        self.clicked.connect(self._open)

    def set_rgb(self, rgb: int):
        self.rgb = rgb
        self.update()

    def _open(self):
        pop = ColorPopover(self.rgb, self.swatches, self.window())
        pop.colorChanged.connect(self._picked)
        pop.popup_at(self)

    def _picked(self, rgb):
        self.set_rgb(rgb)
        self.colorChanged.emit(rgb)

    def paintEvent(self, _e):
        t = theme()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if not self.isEnabled():
            p.setOpacity(0.45)
        r = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        p.setPen(QPen(t.c("border-strong" if self.underMouse() else "border"), 1))
        p.setBrush(t.c("surface-2"))
        p.drawRoundedRect(r, 8, 8)
        edge = QColor(255, 255, 255, 36) if t.dark else QColor(18, 22, 28, 40)
        p.setPen(QPen(edge, 1))
        p.setBrush(qcolor(self.rgb))
        p.drawRoundedRect(QRectF(4, 4, 24, 24), 5, 5)
        p.setPen(t.c("text-1"))
        p.setFont(font(12.5, 500, mono=True))
        p.drawText(QRectF(36, 0, self.width() - 60, self.height()), Qt.AlignVCenter | Qt.AlignLeft,
                   f"#{self.rgb:06X}")
        p.drawPixmap(self.width() - 22, 8, t.pixmap("chevron-abajo", "text-2", 16))

    def enterEvent(self, e):
        self.update()

    def leaveEvent(self, e):
        self.update()


def connect_theme_refresh():
    theme().changed.connect(_refresh_icons)


__all__ = [n for n in dir() if not n.startswith("_")]