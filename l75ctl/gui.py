"""Interfaz grafica (PySide6) para el ROYALAXE / ProtoArc L75."""

from __future__ import annotations

import sys
import time
import traceback

from PySide6.QtCore import QObject, QRectF, QRunnable, Qt, QThreadPool, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QFont, QFontMetricsF, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QApplication, QCheckBox, QColorDialog, QComboBox, QFileDialog, QFormLayout,
                               QGridLayout, QGroupBox, QHBoxLayout, QLabel, QListWidget, QMainWindow,
                               QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QSlider, QSpinBox,
                               QStackedWidget, QTabWidget, QVBoxLayout, QWidget)

from . import __version__
from . import lcd
from . import lighting as L
from . import protocol as P
from .keyboard import L75, KeyboardOptions, SleepTimes
from .keymap import (FUNCTIONS, HID_NAMES, KEYS, MACRO_MODE_LABELS, MOUSE, Action, PhysicalKey, hid_name)
from .macros import Macro, encoded_length, parse_macro_text
from .transport import TransportError

# --------------------------------------------------------------------- tareas


class _Signals(QObject):
    done = Signal(object)
    failed = Signal(str)
    progress = Signal(float, str)


class Task(QRunnable):
    def __init__(self, func, /, *args, progress: bool = False, **kwargs):
        super().__init__()
        self.func, self.args, self.kwargs, self.use_progress = func, args, kwargs, progress
        self.signals = _Signals()
        self.cancelled = False

    def run(self):
        try:
            if self.use_progress:
                self.kwargs["progress"] = lambda f, m: self.signals.progress.emit(f, m)
            self.signals.done.emit(self.func(*self.args, **self.kwargs))
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            self.signals.failed.emit(str(exc))


# --------------------------------------------------------------------- teclado dibujado


class KeyboardWidget(QWidget):
    keyClicked = Signal(object)

    MARGIN = 8

    def __init__(self, parent=None):
        super().__init__(parent)
        self.labels: dict[int, str] = {}
        self.colors: dict[int, QColor] = {}
        self.changed: set[int] = set()
        self.selected: int | None = None
        self.max_x = max(k.x + k.w for k in KEYS)
        self.max_y = max(k.y + k.h for k in KEYS)
        self.setMinimumSize(620, 250)
        self.setMouseTracking(True)

    def _geom(self):
        w, h = self.width() - 2 * self.MARGIN, self.height() - 2 * self.MARGIN
        s = min(w / self.max_x, h / self.max_y)
        ox = self.MARGIN + (w - self.max_x * s) / 2
        oy = self.MARGIN + (h - self.max_y * s) / 2
        return s, ox, oy

    def key_rect(self, k: PhysicalKey) -> QRectF:
        s, ox, oy = self._geom()
        return QRectF(ox + k.x * s, oy + k.y * s, k.w * s, k.h * s)

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        pal = self.palette()
        base = pal.window().color()
        dark = base.lightness() < 128
        keycap = QColor("#3a3d45") if dark else QColor("#e8e9ee")
        text = pal.windowText().color()
        accent = pal.highlight().color()
        s, _, _ = self._geom()
        small = QFont(self.font())
        small.setPointSizeF(max(6.0, 7.0 * s))
        big = QFont(self.font())
        big.setPointSizeF(max(6.5, 8.0 * s))
        big.setBold(True)
        for k in KEYS:
            r = self.key_rect(k)
            fill = self.colors.get(k.slot, keycap)
            p.setBrush(fill)
            pen = QPen(accent if k.slot == self.selected else QColor(0, 0, 0, 80))
            pen.setWidthF(3 if k.slot == self.selected else 1)
            p.setPen(pen)
            p.drawRoundedRect(r.adjusted(1, 1, -1, -1), 4, 4)
            fg = text
            if k.slot in self.colors:
                c = self.colors[k.slot]
                fg = QColor("black") if c.lightness() > 140 else QColor("white")
            label = self.labels.get(k.slot)
            p.setPen(fg)
            inner = r.adjusted(3, 2, -3, -2)
            if label is not None and k.slot in self.changed:
                p.setFont(_fit(small, k.name, inner.width()))
                p.drawText(inner, Qt.AlignTop | Qt.AlignLeft, k.name)
                p.setFont(_fit(big, label, inner.width()))
                if k.slot not in self.colors:
                    p.setPen(accent)
                p.drawText(inner.adjusted(0, inner.height() * 0.3, 0, 0), Qt.AlignCenter, label)
            else:
                p.setFont(_fit(small, k.name, inner.width()))
                p.drawText(inner, Qt.AlignCenter, k.name)
        p.end()

    def mousePressEvent(self, ev):
        pos = ev.position()
        for k in KEYS:
            if self.key_rect(k).contains(pos):
                self.selected = k.slot
                self.update()
                self.keyClicked.emit(k)
                return


def _fit(font: QFont, text: str, width: float) -> QFont:
    f = QFont(font)
    while f.pointSizeF() > 5 and QFontMetricsF(f).horizontalAdvance(text) > width:
        f.setPointSizeF(f.pointSizeF() - 0.5)
    return f


def color_button_style(btn: QPushButton, rgb: int) -> None:
    c = QColor((rgb >> 16) & 255, (rgb >> 8) & 255, rgb & 255)
    fg = "black" if c.lightness() > 140 else "white"
    btn.setStyleSheet(f"background-color: {c.name()}; color: {fg};")
    btn.setText(c.name().upper())


# --------------------------------------------------------------------- pestañas


class BaseTab(QWidget):
    def __init__(self, win: "MainWindow"):
        super().__init__()
        self.win = win

    @property
    def kb(self) -> L75 | None:
        return self.win.kb

    def on_connected(self):
        pass


class KeysTab(BaseTab):
    def __init__(self, win):
        super().__init__(win)
        self.actions: list[Action] = []
        self.fn = False
        lay = QVBoxLayout(self)

        top = QHBoxLayout()
        self.layer = QComboBox()
        self.layer.addItems(["Capa normal", "Capa Fn (Fn + tecla)"])
        self.layer.currentIndexChanged.connect(self._layer_changed)
        btn_read = QPushButton("Leer del teclado")
        btn_read.clicked.connect(self.load)
        btn_reset = QPushButton("Restaurar todas")
        btn_reset.clicked.connect(self.reset_all)
        top.addWidget(QLabel("Capa:"))
        top.addWidget(self.layer)
        top.addStretch()
        top.addWidget(btn_read)
        top.addWidget(btn_reset)
        lay.addLayout(top)

        self.kbw = KeyboardWidget()
        self.kbw.keyClicked.connect(self.select_key)
        lay.addWidget(self.kbw, 1)

        box = QGroupBox("Tecla seleccionada")
        bl = QGridLayout(box)
        self.sel_label = QLabel("Haz clic en una tecla")
        self.cur_label = QLabel("")
        self.kind = QComboBox()
        self.kind.addItems(["Tecla", "Combinacion", "Multimedia / funcion", "Raton", "Macro",
                            "Desactivada", "Valor por defecto"])
        self.stack = QStackedWidget()
        # tecla
        self.key_combo = self._hid_combo()
        self.stack.addWidget(self.key_combo)
        # combinacion
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        self.combo_keys = [self._hid_combo(allow_none=True) for _ in range(3)]
        for i, c in enumerate(self.combo_keys):
            if i:
                h.addWidget(QLabel("+"))
            h.addWidget(c)
        self.stack.addWidget(w)
        # funcion
        self.func_combo = QComboBox()
        for key, label, raw in FUNCTIONS:
            self.func_combo.addItem(label, raw)
        self.stack.addWidget(self.func_combo)
        # raton
        self.mouse_combo = QComboBox()
        for key, label, raw in MOUSE:
            self.mouse_combo.addItem(label, raw)
        self.stack.addWidget(self.mouse_combo)
        # macro
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        self.macro_idx = QSpinBox()
        self.macro_idx.setRange(0, P.MACRO_MAX - 1)
        self.macro_mode = QComboBox()
        for code, label in MACRO_MODE_LABELS.items():
            self.macro_mode.addItem(label, code)
        h.addWidget(QLabel("Macro n°"))
        h.addWidget(self.macro_idx)
        h.addWidget(QLabel("Modo"))
        h.addWidget(self.macro_mode)
        self.stack.addWidget(w)
        self.stack.addWidget(QLabel("La tecla no hara nada."))
        self.stack.addWidget(QLabel("Vuelve a la funcion original de la tecla."))
        self.kind.currentIndexChanged.connect(self.stack.setCurrentIndex)
        self.apply_btn = QPushButton("Aplicar")
        self.apply_btn.clicked.connect(self.apply)
        bl.addWidget(self.sel_label, 0, 0, 1, 2)
        bl.addWidget(self.cur_label, 0, 2, 1, 2)
        bl.addWidget(QLabel("Nueva accion:"), 1, 0)
        bl.addWidget(self.kind, 1, 1)
        bl.addWidget(self.stack, 1, 2)
        bl.addWidget(self.apply_btn, 1, 3)
        lay.addWidget(box)
        self.selected: PhysicalKey | None = None

    def _hid_combo(self, allow_none=False) -> QComboBox:
        c = QComboBox()
        c.setEditable(True)
        c.setInsertPolicy(QComboBox.NoInsert)
        if allow_none:
            c.addItem("(nada)", 0)
        for code in sorted(HID_NAMES):
            c.addItem(HID_NAMES[code], code)
        return c

    def on_connected(self):
        self.load()

    def _layer_changed(self, i):
        self.fn = i == 1
        self.kind.model().item(6).setEnabled(not self.fn)
        self.load()

    def load(self):
        if not self.kb:
            return
        self.win.run(self.kb.read_matrix, on_done=self._loaded, progress=True, fn=self.fn,
                     label="Leyendo asignaciones...")

    def _loaded(self, actions):
        self.actions = actions
        self.refresh()

    def refresh(self):
        self.kbw.labels.clear()
        self.kbw.changed.clear()
        for k in KEYS:
            if k.slot < len(self.actions):
                a = self.actions[k.slot]
                if self.fn:
                    if a.raw != (0, 0, 0, 0):
                        self.kbw.labels[k.slot] = a.short()
                        self.kbw.changed.add(k.slot)
                else:
                    self.kbw.labels[k.slot] = a.short()
                    if a != k.default_action:
                        self.kbw.changed.add(k.slot)
        self.kbw.update()
        if self.selected:
            self.select_key(self.selected)

    def select_key(self, k: PhysicalKey):
        self.selected = k
        self.sel_label.setText(f"<b>{k.name}</b> (slot {k.slot})")
        cur = self.actions[k.slot] if k.slot < len(self.actions) else None
        self.cur_label.setText("Actual: " + (cur.describe() if cur else "?"))
        if cur:
            self._show_action(cur)

    def _show_action(self, a: Action):
        kind = a.kind
        t, x, y, z = a.raw
        if kind == "key":
            self.kind.setCurrentIndex(0)
            self.key_combo.setCurrentIndex(max(0, self.key_combo.findData(y)))
        elif kind == "combo":
            self.kind.setCurrentIndex(1)
            for c, v in zip(self.combo_keys, (x, y, z)):
                c.setCurrentIndex(max(0, c.findData(v)))
        elif kind == "function" or kind == "media":
            self.kind.setCurrentIndex(2)
            i = self.func_combo.findData(a.raw)
            if i >= 0:
                self.func_combo.setCurrentIndex(i)
        elif kind == "mouse":
            self.kind.setCurrentIndex(3)
            i = self.mouse_combo.findData(a.raw)
            if i >= 0:
                self.mouse_combo.setCurrentIndex(i)
        elif kind == "macro":
            self.kind.setCurrentIndex(4)
            self.macro_idx.setValue(y)
            self.macro_mode.setCurrentIndex(max(0, self.macro_mode.findData(x)))
        elif kind == "off":
            self.kind.setCurrentIndex(5)

    def _combo_value(self, c: QComboBox) -> int:
        i = c.findText(c.currentText())
        return c.itemData(i) if i >= 0 else c.currentData()

    def build_action(self) -> Action:
        i = self.kind.currentIndex()
        if i == 0:
            return Action.key(self._combo_value(self.key_combo))
        if i == 1:
            codes = [self._combo_value(c) for c in self.combo_keys]
            codes = [c for c in codes if c]
            return Action.combo(codes)
        if i == 2:
            return Action(tuple(self.func_combo.currentData()))
        if i == 3:
            return Action(tuple(self.mouse_combo.currentData()))
        if i == 4:
            return Action.macro(self.macro_idx.value(), self.macro_mode.currentData())
        if i == 5:
            return Action.disabled()
        return self.selected.default_action

    def apply(self):
        if not self.kb or not self.selected:
            return
        try:
            act = self.build_action()
        except ValueError as e:
            QMessageBox.warning(self, "Accion invalida", str(e))
            return
        k = self.selected

        def done(_):
            if k.slot < len(self.actions):
                self.actions[k.slot] = act
            self.refresh()
            self.win.status(f"{k.name} -> {act.describe()}")

        self.win.run(self.kb.set_key, k, act, fn=self.fn, on_done=done, label=f"Asignando {k.name}...")

    def reset_all(self):
        if not self.kb or self.fn:
            return
        if QMessageBox.question(self, "Restaurar", "¿Restaurar todas las teclas de este perfil?") != QMessageBox.Yes:
            return

        def work():
            for k in KEYS:
                self.kb.set_key(k, k.default_action)

        self.win.run(work, on_done=lambda _: self.load(), label="Restaurando teclas...")


class LightPanel(QGroupBox):
    def __init__(self, title, modes, tab: "LightTab", side: bool):
        super().__init__(title)
        self.modes, self.tab, self.side = modes, tab, side
        self.color = 0xFFFFFF
        f = QFormLayout(self)
        self.mode = QComboBox()
        for m in modes:
            self.mode.addItem(m.label, m.key)
        self.mode.currentIndexChanged.connect(self._mode_changed)
        self.bright = QSlider(Qt.Horizontal)
        self.bright.setRange(0, 4)
        self.bright.setValue(4)
        self.speed = QSlider(Qt.Horizontal)
        self.speed.setRange(0, 4)
        self.speed.setValue(2)
        self.color_btn = QPushButton()
        self.color_btn.clicked.connect(self.pick_color)
        color_button_style(self.color_btn, self.color)
        self.rainbow = QCheckBox("Arcoiris (colores ciclicos)")
        self.option = QComboBox()
        f.addRow("Modo", self.mode)
        f.addRow("Brillo", self.bright)
        f.addRow("Velocidad", self.speed)
        f.addRow("Color", self.color_btn)
        f.addRow("", self.rainbow)
        f.addRow("Opcion", self.option)
        row = QHBoxLayout()
        b_get = QPushButton("Leer")
        b_get.clicked.connect(self.read)
        b_set = QPushButton("Aplicar")
        b_set.clicked.connect(self.apply)
        row.addWidget(b_get)
        row.addWidget(b_set)
        f.addRow(row)
        self._mode_changed()

    def mdef(self):
        return self.modes[self.mode.currentIndex()]

    def _mode_changed(self):
        m = self.mdef()
        self.speed.setEnabled(m.speed)
        self.color_btn.setEnabled(m.color or m.kind == "music")
        self.rainbow.setEnabled(m.color or m.kind == "music")
        self.bright.setEnabled(m.kind not in ("off", "screen"))
        self.option.clear()
        if m.kind == "picture":
            for i in range(1, 6):
                self.option.addItem(f"Imagen {i}", str(i))
        else:
            for key, label in zip(m.options, m.option_labels):
                self.option.addItem(label, key)
        self.option.setEnabled(self.option.count() > 0)

    def pick_color(self):
        c = QColorDialog.getColor(QColor(f"#{self.color:06x}"), self, "Color")
        if c.isValid():
            self.color = (c.red() << 16) | (c.green() << 8) | c.blue()
            color_button_style(self.color_btn, self.color)

    def setting(self) -> L.LightSetting:
        return L.LightSetting(mode=self.mdef().key, brightness=self.bright.value(), speed=self.speed.value(),
                              color=self.color, rainbow=self.rainbow.isChecked(),
                              option=self.option.currentData() if self.option.count() else None)

    def show_setting(self, s: L.LightSetting):
        i = self.mode.findData(s.mode)
        if i >= 0:
            self.mode.setCurrentIndex(i)
        self.bright.setValue(s.brightness)
        self.speed.setValue(s.speed)
        self.color = s.color
        color_button_style(self.color_btn, s.color)
        self.rainbow.setChecked(s.rainbow)
        if s.option is not None:
            j = self.option.findData(s.option)
            if j >= 0:
                self.option.setCurrentIndex(j)

    def read(self):
        kb = self.tab.kb
        if kb:
            self.tab.win.run(kb.get_side_light if self.side else kb.get_light, on_done=self.show_setting,
                             label="Leyendo luz...")

    def apply(self):
        kb = self.tab.kb
        if kb:
            s = self.setting()
            self.tab.win.run(kb.set_side_light if self.side else kb.set_light, s,
                             on_done=lambda _: self.tab.win.status("Luz: " + s.describe(self.side)),
                             label="Aplicando luz...")


class LightTab(BaseTab):
    def __init__(self, win):
        super().__init__(win)
        lay = QHBoxLayout(self)
        self.keys = LightPanel("Iluminacion de teclas", L.MODES, self, side=False)
        self.side = LightPanel("Tira de luz lateral", L.SIDE_MODES, self, side=True)
        lay.addWidget(self.keys)
        lay.addWidget(self.side)

    def on_connected(self):
        self.keys.read()
        self.side.read()


class KeyColorsTab(BaseTab):
    def __init__(self, win):
        super().__init__(win)
        self.color = 0xFF0000
        self.slot_colors: dict[int, int] = {}
        lay = QVBoxLayout(self)
        info = QLabel("Pinta cada tecla con su color. Se usa en el modo de luz <b>Imagen de usuario</b>. "
                      "Cada clic se envia al teclado al instante.")
        info.setWordWrap(True)
        lay.addWidget(info)
        row = QHBoxLayout()
        self.color_btn = QPushButton()
        self.color_btn.clicked.connect(self.pick)
        color_button_style(self.color_btn, self.color)
        b_read = QPushButton("Leer colores")
        b_read.clicked.connect(self.load)
        b_all = QPushButton("Pintar todas")
        b_all.clicked.connect(self.paint_all)
        b_mode = QPushButton("Activar modo Imagen de usuario")
        b_mode.clicked.connect(self.activate)
        row.addWidget(QLabel("Pincel:"))
        row.addWidget(self.color_btn)
        row.addStretch()
        row.addWidget(b_read)
        row.addWidget(b_all)
        row.addWidget(b_mode)
        lay.addLayout(row)
        self.kbw = KeyboardWidget()
        self.kbw.keyClicked.connect(self.paint)
        lay.addWidget(self.kbw, 1)

    def pick(self):
        c = QColorDialog.getColor(QColor(f"#{self.color:06x}"), self, "Color del pincel")
        if c.isValid():
            self.color = (c.red() << 16) | (c.green() << 8) | c.blue()
            color_button_style(self.color_btn, self.color)

    def _show(self):
        self.kbw.colors = {s: QColor(f"#{c:06x}") for s, c in self.slot_colors.items()}
        self.kbw.update()

    def load(self):
        if self.kb:
            self.win.run(self.kb.get_key_colors, on_done=self._loaded, label="Leyendo colores...")

    def _loaded(self, colors):
        self.slot_colors = {k.slot: colors[k.slot] for k in KEYS}
        self._show()

    def paint(self, k: PhysicalKey):
        if not self.kb:
            return
        color = self.color
        self.slot_colors[k.slot] = color
        self._show()
        self.win.run(self.kb.set_key_color, k, color, label=f"Color {k.name}", quiet=True)

    def paint_all(self):
        if not self.kb:
            return
        color = self.color

        def work(progress):
            for i, k in enumerate(KEYS):
                self.kb.set_key_color(k, color)
                progress((i + 1) / len(KEYS), "pintando")

        for k in KEYS:
            self.slot_colors[k.slot] = color
        self._show()
        self.win.run(work, progress=True, label="Pintando todas las teclas...")

    def activate(self):
        if self.kb:
            s = L.LightSetting(mode="user", brightness=4, option="1")
            self.win.run(self.kb.set_light, s, label="Activando modo imagen de usuario...")


class MacrosTab(BaseTab):
    def __init__(self, win):
        super().__init__(win)
        lay = QHBoxLayout(self)
        self.list = QListWidget()
        for i in range(P.MACRO_MAX):
            self.list.addItem(f"Macro {i}")
        self.list.setCurrentRow(0)
        self.list.setMaximumWidth(140)
        lay.addWidget(self.list)
        right = QVBoxLayout()
        help_ = QLabel(
            "Escribe los eventos separados por comas:<br>"
            "<code>down:ctrl, tap:c, up:ctrl, delay:50, tap:enter</code><br>"
            "<code>down:&lt;tecla&gt;</code> pulsar, <code>up:&lt;tecla&gt;</code> soltar, "
            "<code>tap:&lt;tecla&gt;</code> pulsar y soltar, <code>delay:&lt;ms&gt;</code> esperar, "
            "<code>down:mouse-left</code> raton.<br>"
            "Despues asignala a una tecla en la pestaña <b>Teclas</b> (tipo Macro).")
        help_.setWordWrap(True)
        help_.setTextFormat(Qt.RichText)
        right.addWidget(help_)
        self.text = QPlainTextEdit()
        self.text.setPlaceholderText("down:ctrl, tap:c, up:ctrl")
        self.text.textChanged.connect(self.validate)
        right.addWidget(self.text, 1)
        self.preview = QLabel("")
        self.preview.setWordWrap(True)
        right.addWidget(self.preview)
        row = QHBoxLayout()
        self.repeat = QSpinBox()
        self.repeat.setRange(1, 65535)
        row.addWidget(QLabel("Repeticiones:"))
        row.addWidget(self.repeat)
        row.addStretch()
        b_read = QPushButton("Leer del teclado")
        b_read.clicked.connect(self.read)
        b_save = QPushButton("Guardar en el teclado")
        b_save.clicked.connect(self.save)
        b_clear = QPushButton("Borrar")
        b_clear.clicked.connect(self.clear)
        row.addWidget(b_read)
        row.addWidget(b_clear)
        row.addWidget(b_save)
        right.addLayout(row)
        lay.addLayout(right, 1)
        self.list.currentRowChanged.connect(lambda _: self.read())

    def validate(self) -> Macro | None:
        try:
            events = parse_macro_text(self.text.toPlainText())
            n = encoded_length(events)
            ok = n <= P.MACRO_MAX_BYTES
            desc = "; ".join(e.describe() for e in events[:12]) + (" ..." if len(events) > 12 else "")
            self.preview.setText(f"{len(events)} eventos, {n}/{P.MACRO_MAX_BYTES} bytes"
                                 + ("" if ok else "  ⚠ demasiado larga") + (f"<br>{desc}" if desc else ""))
            return Macro(events, self.repeat.value()) if ok else None
        except (ValueError, KeyError) as e:
            self.preview.setText(f"⚠ {e}")
            return None

    def read(self):
        if not self.kb:
            return
        idx = self.list.currentRow()
        self.win.run(self.kb.read_macro, idx, on_done=self._loaded, label=f"Leyendo macro {idx}...")

    def _loaded(self, m: Macro):
        self.text.setPlainText(m.to_text())
        self.repeat.setValue(max(1, m.repeat))

    def save(self):
        if not self.kb:
            return
        m = self.validate()
        if m is None:
            QMessageBox.warning(self, "Macro", "Corrige la macro antes de guardar.")
            return
        idx = self.list.currentRow()
        self.win.run(self.kb.write_macro, idx, m, on_done=lambda _: self.win.status(f"Macro {idx} guardada"),
                     label=f"Guardando macro {idx}...")

    def clear(self):
        if not self.kb:
            return
        idx = self.list.currentRow()
        self.text.setPlainText("")
        self.win.run(self.kb.write_macro, idx, Macro([], 0), label=f"Borrando macro {idx}...")


class ScreenTab(BaseTab):
    def __init__(self, win):
        super().__init__(win)
        self.anim: lcd.Animation | None = None
        self.path: str | None = None
        self.frame_i = 0
        self.task: Task | None = None
        lay = QVBoxLayout(self)
        info = QLabel("Pantalla de 240×135. La subida solo funciona <b>por cable</b>. "
                      "En el teclado, <b>Fn+Ctrl</b> alterna entre tu imagen y el estilo por defecto.")
        info.setWordWrap(True)
        lay.addWidget(info)
        row = QHBoxLayout()
        b_open = QPushButton("Elegir imagen o GIF…")
        b_open.clicked.connect(self.choose)
        self.fit = QComboBox()
        self.fit.addItem("Ajustar (bandas negras)", "contain")
        self.fit.addItem("Rellenar (recortar)", "cover")
        self.fit.addItem("Estirar", "stretch")
        self.fit.currentIndexChanged.connect(self.reload)
        self.delay = QSpinBox()
        self.delay.setRange(0, 255)
        self.delay.setSuffix(" ms")
        self.delay.setToolTip("Tiempo entre cuadros (20..255 ms)")
        self.delay.valueChanged.connect(self._delay_changed)
        row.addWidget(b_open)
        row.addWidget(QLabel("Modo:"))
        row.addWidget(self.fit)
        row.addWidget(QLabel("Retardo:"))
        row.addWidget(self.delay)
        row.addStretch()
        lay.addLayout(row)
        self.preview = QLabel("Sin imagen")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setFixedSize(lcd.W * 2 + 8, lcd.H * 2 + 8)
        self.preview.setStyleSheet("background:#000; color:#888; border:4px solid #222; border-radius:6px;")
        lay.addWidget(self.preview, 0, Qt.AlignCenter)
        self.details = QLabel("")
        lay.addWidget(self.details, 0, Qt.AlignCenter)
        self.bar = QProgressBar()
        self.bar.setVisible(False)
        lay.addWidget(self.bar)
        row2 = QHBoxLayout()
        self.b_up = QPushButton("Subir a la pantalla")
        self.b_up.clicked.connect(self.upload)
        self.b_cancel = QPushButton("Cancelar")
        self.b_cancel.setVisible(False)
        self.b_cancel.clicked.connect(self.cancel)
        b_time = QPushButton("Sincronizar fecha y hora")
        b_time.clicked.connect(self.sync_time)
        row2.addWidget(b_time)
        row2.addStretch()
        row2.addWidget(self.b_cancel)
        row2.addWidget(self.b_up)
        lay.addLayout(row2)
        lay.addStretch()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)

    def choose(self):
        path, _ = QFileDialog.getOpenFileName(self, "Imagen o GIF", "",
                                              "Imagenes (*.gif *.png *.jpg *.jpeg *.webp *.bmp);;Todos (*)")
        if path:
            self.path = path
            self.reload(reset_delay=True)

    def reload(self, *_a, reset_delay=False):
        if not self.path:
            return
        try:
            delay = None if reset_delay else self.delay.value()
            self.anim = lcd.load_animation(self.path, fit=self.fit.currentData(), delay_ms=delay)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Imagen", f"No pude abrir la imagen:\n{e}")
            return
        self.delay.blockSignals(True)
        self.delay.setValue(self.anim.delay_ms)
        self.delay.blockSignals(False)
        box = lcd.content_box(self.anim.frames)
        pk = lcd.estimate_packets(self.anim)
        self.details.setText(f"{len(self.anim.frames)} cuadro(s) · area {box.width}×{box.height} · "
                             f"{pk} paquetes (~{pk * 2.5 / 1000:.0f} s)")
        self.frame_i = 0
        self._show_frame()
        self.timer.stop()
        if len(self.anim.frames) > 1:
            self.timer.start(max(20, self.anim.delay_ms))

    def _delay_changed(self, v):
        if self.anim:
            self.anim.delay_ms = v
            if self.timer.isActive():
                self.timer.start(max(20, v))

    def _show_frame(self):
        if not self.anim:
            return
        f = self.anim.frames[self.frame_i]
        data = f.tobytes("raw", "RGB")
        img = QImage(data, f.width, f.height, f.width * 3, QImage.Format_RGB888).copy()
        self.preview.setPixmap(QPixmap.fromImage(img).scaled(lcd.W * 2, lcd.H * 2))

    def _tick(self):
        if self.anim:
            self.frame_i = (self.frame_i + 1) % len(self.anim.frames)
            self._show_frame()

    def upload(self):
        if not self.kb or not self.anim:
            QMessageBox.information(self, "Pantalla", "Primero elige una imagen y conecta el teclado.")
            return
        if self.kb.bus == "bt":
            QMessageBox.information(self, "Pantalla", "Subir imagenes solo funciona por cable USB-C, "
                                    "no por Bluetooth (igual que en el driver oficial).")
            return
        self.bar.setVisible(True)
        self.bar.setValue(0)
        self.b_up.setEnabled(False)
        self.b_cancel.setVisible(True)
        t0 = time.time()

        def done(_):
            self._finish()
            self.win.status(f"Imagen subida en {time.time() - t0:.0f} s. Pulsa Fn+Ctrl si no la ves.")

        self.task = self.win.run(self.kb.upload_animation, self.anim, progress=True, on_done=done,
                                 on_error=lambda _e: self._finish(), on_progress=self._progress,
                                 cancel=lambda: bool(self.task and self.task.cancelled),
                                 label="Subiendo imagen...")

    def _progress(self, f, msg):
        self.bar.setValue(int(f * 100))
        self.bar.setFormat(f"%p%  {msg}")

    def _finish(self):
        self.bar.setVisible(False)
        self.b_up.setEnabled(True)
        self.b_cancel.setVisible(False)
        self.task = None

    def cancel(self):
        if self.task:
            self.task.cancelled = True

    def sync_time(self):
        if self.kb:
            self.win.run(self.kb.sync_clock,
                         on_done=lambda t: self.win.status("Hora sincronizada: " + t.strftime("%H:%M:%S")),
                         label="Sincronizando hora...")


class SettingsTab(BaseTab):
    def __init__(self, win):
        super().__init__(win)
        lay = QVBoxLayout(self)
        g = QGroupBox("Rendimiento")
        f = QFormLayout(g)
        self.rate = QComboBox()
        for hz in (125, 250, 500, 1000):
            self.rate.addItem(f"{hz} Hz", hz)
        self.debounce = QSpinBox()
        self.debounce.setRange(0, 50)
        self.debounce.setSuffix(" ms")
        f.addRow("Tasa de sondeo", self.rate)
        f.addRow("Debounce", self.debounce)
        lay.addWidget(g)
        g = QGroupBox("Reposo (modo inalambrico)")
        f = QFormLayout(g)
        self.sleep = QSpinBox()
        self.sleep.setRange(0, 60)
        self.sleep.setSuffix(" min")
        self.sleep.setSpecialValueText("nunca")
        self.deep = QSpinBox()
        self.deep.setRange(10, 60)
        self.deep.setSuffix(" min")
        f.addRow("Reposo", self.sleep)
        f.addRow("Reposo profundo", self.deep)
        lay.addWidget(g)
        g = QGroupBox("Opciones")
        v = QVBoxLayout(g)
        self.win_lock = QCheckBox("Bloquear tecla Windows")
        self.mac = QCheckBox("Modo Mac")
        self.wasd = QCheckBox("Intercambiar WASD y flechas")
        for w in (self.win_lock, self.mac, self.wasd):
            v.addWidget(w)
        lay.addWidget(g)
        row = QHBoxLayout()
        b_read = QPushButton("Leer")
        b_read.clicked.connect(self.load)
        b_apply = QPushButton("Aplicar")
        b_apply.clicked.connect(self.apply)
        b_reset = QPushButton("Restaurar de fabrica…")
        b_reset.clicked.connect(self.factory)
        row.addWidget(b_reset)
        row.addStretch()
        row.addWidget(b_read)
        row.addWidget(b_apply)
        lay.addLayout(row)
        self.info = QLabel("")
        lay.addWidget(self.info)
        lay.addStretch()
        self.opts = KeyboardOptions()

    def on_connected(self):
        self.load()

    def load(self):
        if not self.kb:
            return
        kb = self.kb

        def work():
            return (kb.get_report_rate(), kb.get_debounce(), kb.get_sleep(), kb.get_options(),
                    kb.firmware_version(), kb.battery())

        self.win.run(work, on_done=self._loaded, label="Leyendo ajustes...")

    def _loaded(self, r):
        rate, deb, sl, opts, fw, bat = r
        if rate:
            self.rate.setCurrentIndex(max(0, self.rate.findData(rate)))
        self.debounce.setValue(deb)
        self.sleep.setValue(min(60, sl.bt // 60))
        self.deep.setValue(max(10, min(60, sl.deep_bt // 60)))
        self.opts = opts
        self.win_lock.setChecked(opts.win_lock)
        self.mac.setChecked(opts.mac_mode)
        self.wasd.setChecked(opts.wasd_arrows_swap)
        self.info.setText(f"Firmware {fw >> 8}.{fw & 0xFF:02d} · Bateria {bat[0]}% ({bat[1]})")

    def apply(self):
        if not self.kb:
            return
        kb = self.kb
        o = self.opts
        o.win_lock, o.mac_mode, o.wasd_arrows_swap = (self.win_lock.isChecked(), self.mac.isChecked(),
                                                      self.wasd.isChecked())
        sl = SleepTimes(self.sleep.value() * 60, self.sleep.value() * 60, self.deep.value() * 60,
                        self.deep.value() * 60)
        rate, deb = self.rate.currentData(), self.debounce.value()

        def work():
            kb.set_report_rate(rate)
            kb.set_debounce(deb)
            kb.set_sleep(sl)
            kb.set_options(o)

        self.win.run(work, on_done=lambda _: self.win.status("Ajustes guardados"), label="Guardando ajustes...")

    def factory(self):
        if not self.kb:
            return
        if QMessageBox.warning(self, "Restaurar de fabrica",
                               "Se borraran TODAS las teclas, macros y luces personalizadas. ¿Continuar?",
                               QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        self.win.run(self.kb.factory_reset, on_done=lambda _: self.win.on_connected(),
                     label="Restaurando de fabrica...")


# --------------------------------------------------------------------- ventana


class MainWindow(QMainWindow):
    def __init__(self, demo: bool = False):
        super().__init__()
        self.setWindowTitle(f"L75 Config {__version__} — ROYALAXE / ProtoArc L75")
        self.resize(1000, 640)
        self.kb: L75 | None = None
        self.pool = QThreadPool.globalInstance()
        self._tasks: set[Task] = set()

        central = QWidget()
        v = QVBoxLayout(central)
        top = QHBoxLayout()
        self.conn_label = QLabel("Desconectado")
        self.profile = QComboBox()
        self.profile.addItems(["Perfil 1", "Perfil 2", "Perfil 3"])
        self.profile.activated.connect(self.change_profile)
        b_conn = QPushButton("Conectar")
        b_conn.clicked.connect(lambda: self.connect_device(False))
        top.addWidget(self.conn_label, 1)
        top.addWidget(QLabel("Perfil:"))
        top.addWidget(self.profile)
        top.addWidget(b_conn)
        v.addLayout(top)

        self.tabs = QTabWidget()
        self.tab_list = [
            ("Teclas", KeysTab(self)), ("Iluminacion", LightTab(self)),
            ("Colores por tecla", KeyColorsTab(self)), ("Macros", MacrosTab(self)),
            ("Pantalla", ScreenTab(self)), ("Ajustes", SettingsTab(self)),
        ]
        for name, tab in self.tab_list:
            self.tabs.addTab(tab, name)
        v.addWidget(self.tabs, 1)
        self.setCentralWidget(central)

        m = self.menuBar().addMenu("&Conexion")
        a = QAction("Conectar teclado", self)
        a.triggered.connect(lambda: self.connect_device(False))
        m.addAction(a)
        a = QAction("Modo demo (sin teclado)", self)
        a.triggered.connect(lambda: self.connect_device(True))
        m.addAction(a)
        m = self.menuBar().addMenu("&Ayuda")
        a = QAction("Acerca de", self)
        a.triggered.connect(self.about)
        m.addAction(a)

        self.busy = QLabel("")
        self.statusBar().addPermanentWidget(self.busy)
        QTimer.singleShot(100, lambda: self.connect_device(demo, quiet=not demo))

    # ---------------------------------------------------------------- tareas
    def run(self, func, /, *args, on_done=None, on_error=None, on_progress=None, progress=False, label="",
            quiet=False, **kwargs) -> Task:
        task = Task(func, *args, progress=progress, **kwargs)
        self._tasks.add(task)
        if label and not quiet:
            self.busy.setText("⏳ " + label)

        def finished():
            self._tasks.discard(task)
            if not self._tasks:
                self.busy.setText("")

        def ok(result):
            finished()
            if on_done:
                on_done(result)

        def fail(msg):
            finished()
            if on_error:
                on_error(msg)
            QMessageBox.warning(self, "Error", msg)

        task.signals.done.connect(ok)
        task.signals.failed.connect(fail)
        if on_progress:
            task.signals.progress.connect(on_progress)
        elif progress:
            task.signals.progress.connect(lambda f, m: self.busy.setText(f"⏳ {label} {f * 100:.0f}%"))
        self.pool.start(task)
        return task

    def status(self, msg: str):
        self.statusBar().showMessage(msg, 6000)

    # ---------------------------------------------------------------- conexion
    def connect_device(self, demo: bool, quiet: bool = False):
        if self.kb:
            self.kb.close()
            self.kb = None
        try:
            self.kb = L75.open(demo=demo)
        except TransportError as e:
            self.conn_label.setText("❌ Teclado no encontrado")
            if not quiet:
                r = QMessageBox.question(self, "Sin teclado", f"{e}\n\n¿Abrir en modo demo para probar la app?")
                if r == QMessageBox.Yes:
                    self.connect_device(True)
            else:
                self.status("No se encontro el L75. Menu Conexion → Modo demo para probar sin teclado.")
            return
        if demo:
            self.conn_label.setText("🧪 MODO DEMO (teclado simulado)")
        elif self.kb.bus == "bt":
            self.conn_label.setText("✅ L75 conectado por Bluetooth (la pantalla solo se puede cambiar por cable)")
        else:
            self.conn_label.setText("✅ L75 conectado por cable")
        self.on_connected()

    def on_connected(self):
        def got(p):
            self.profile.setCurrentIndex(p if 0 <= p < 3 else 0)
            for _n, tab in self.tab_list:
                tab.on_connected()

        self.run(self.kb.get_profile, on_done=got, label="Conectando...")

    def change_profile(self, idx):
        if self.kb:
            def done(_):
                self.status(f"Perfil {idx + 1} activo")
                self.tab_list[0][1].load()
            self.run(self.kb.set_profile, idx, on_done=done, label="Cambiando perfil...")

    def about(self):
        QMessageBox.about(self, "Acerca de",
                          f"<b>L75 Config {__version__}</b><br>Configurador libre para Linux del teclado "
                          "ROYALAXE / ProtoArc L75.<br><br>Protocolo obtenido del driver oficial. "
                          "Sin relacion con ProtoArc ni ROYALAXE.")

    def closeEvent(self, ev):
        if self.kb:
            self.kb.close()
        super().closeEvent(ev)


def run(demo: bool = False) -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("L75 Config")
    app.setDesktopFileName("l75-config")
    w = MainWindow(demo=demo)
    w.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(run("--demo" in sys.argv))
