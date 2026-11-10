"""Sección Teclas: reasignación sobre el dibujo del teclado."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QComboBox, QSizePolicy, QStackedWidget, QWidget

from ...keymap import FUNCTIONS, KEYS, MOUSE, SYSTEM_FUNCTIONS, Action, PhysicalKey, is_system
from .. import widgets as W
from ..hidkeys import qt_to_hid
from ..keyboard_view import KeyboardView, KeyLabel
from ..window import Page
from .common import Deck, MiniKey, combo_value, hid_combo, key_display

KIND_INDEX = {"key": 0, "combo": 1, "function": 2, "media": 2, "mouse": 3, "macro": 4, "off": 5}
KINDS = [("Tecla", "teclas"), ("Combinación", "combinacion"), ("Multimedia", "multimedia"), ("Ratón", "raton"),
         ("Macro", "macros"), ("Desactivada", "desactivada"), ("Por defecto", "restaurar")]
MACRO_MODES = [("N veces", 0, "Repite la macro tantas veces como diga la macro"),
               ("Al mantener", 2, "Se repite mientras mantienes la tecla"),
               ("On / off", 1, "Una pulsación la inicia y otra la detiene")]
FUNC_SHORT = {"bright-": "Pant−", "bright+": "Pant+", "vol-": "Vol−", "vol+": "Vol+", "prev": "Ant.", "next": "Sig.",
              "ime": "Idioma", "player": "Música", "calc": "Calc", "mail": "Correo", "mycomputer": "Equipo",
              "search": "Buscar", "home": "Inicio", "back": "Atrás", "refresh": "Recarg.", "lock": "Bloq.",
              "zoom-": "Zoom−", "zoom+": "Zoom+", "mute": "Mudo"}
MEDIA_ICONS = {(3, 0, 205, 0): "play", (3, 0, 183, 0): "detener"}


def legend_for(a: Action) -> tuple[str, str | None]:
    """Texto corto e icono opcional para la cara de la tecla."""
    k = a.kind
    if k == "off":
        return "", "desactivada"
    if k == "system":
        if a.raw == (10, 8, 0, 0):
            return "", "bateria"
        info = SYSTEM_FUNCTIONS.get(a.raw)
        return (info[0] if info else "Sist."), None
    if k == "mouse":
        return "", "raton"
    if k in ("function", "media"):
        ic = MEDIA_ICONS.get(a.raw)
        if ic:
            return "", ic
        short = a.short()
        return FUNC_SHORT.get(short, short[:6]), None
    if k == "key":
        return key_display(a.raw[2]), None
    if k == "combo":
        names = {0xE0: "Ctrl", 0xE1: "⇧", 0xE2: "Alt", 0xE3: "Win", 0xE4: "RCtrl", 0xE5: "⇧", 0xE6: "AltGr",
                 0xE7: "Win"}
        parts = [names.get(x, key_display(x)) for x in a.raw[1:] if x]
        if len(parts) >= 2:
            return "+".join(parts[:-1]) + "+\n" + parts[-1], None
        return "+".join(parts), None
    if k == "macro":
        return f"M{a.raw[2]}", None
    return a.short(), None


class KeyPreview(QWidget):
    """Tecla seleccionada a tamaño grande (panel de edición)."""

    def __init__(self):
        super().__init__()
        self.view = KeyboardView(mode="remap", deck=False)
        self.setFixedSize(172, 92)
        self.key: PhysicalKey | None = None
        self.label: KeyLabel | None = None

    def set(self, k: PhysicalKey | None, lab: KeyLabel | None):
        self.key, self.label = k, lab
        self.update()

    def paintEvent(self, _e):
        from ..theme import theme
        t = theme()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(t.c("border"))
        p.setBrush(t.c("deck"))
        p.drawRoundedRect(QRectF(0.5, 0.5, self.width() - 1, self.height() - 1), 12, 12)
        if not self.key:
            return
        v = self.view
        v.labels = {self.key.slot: self.label} if self.label else {}
        v.selected = self.key.slot
        s = 2.6
        w = min(self.width() - 32, (self.key.w + 7) * s)
        s = w / (self.key.w + 7)
        r = QRectF((self.width() - w) / 2, (self.height() - 32 * s) / 2, w, 32 * s)
        v._key(p, self.key, r, s, 0)


class KeysPage(Page):
    def __init__(self, win):
        super().__init__(win)
        self.actions: list[Action] = []
        self.fn = False
        self.selected: PhysicalKey | None = None
        self.capturing = False

        self.header = W.PageHeader("Teclas", "")
        self.b_read = self.header.add(W.button("Leer del teclado", "secondary", "leer", on_click=self.load))
        self.b_reset = self.header.add(W.button("Restaurar todas…", "ghost", "restaurar", on_click=self.reset_all))
        self.lay.addWidget(self.header)

        # --- teclado
        deck = Deck()
        self.layer = W.Segmented()
        self.layer.add("Normal", False)
        self.layer.add("Fn + tecla", True, icon="capas")
        self.layer.changed.connect(self._layer_changed)
        self.hint = W.label("Lo que hace cada tecla al pulsarla.", "cap")
        self.n_remap = W.label("", "cap")
        self.n_off = W.label("", "cap")
        self.mk_off = MiniKey("off")
        top = W.hbox(self.layer, 4, self.hint, "stretch", MiniKey("remap"), self.n_remap, 10, self.mk_off,
                     self.n_off, spacing=8)
        self.kbv = KeyboardView(mode="remap", deck=False)
        self.kbv.setMaximumWidth(880)
        self.kbv.keyClicked.connect(self.select_key)
        self.kbv.lockedClicked.connect(self.locked_clicked)
        W.vbox(top, W.hbox("stretch", self.kbv, "stretch", spacing=0), spacing=10, margins=(20, 14, 20, 18),
               parent=deck)
        self.lay.addWidget(deck)

        # --- panel de edición
        panel, pl = W.card(padding=(20, 16, 20, 16), spacing=0)
        self.preview = KeyPreview()
        self.sel_name = W.label("Elige una tecla", "sub")
        self.sel_layer = W.label("Capa normal", "cap")
        left = W.vbox(self.preview, 8, self.sel_name, self.sel_layer, "stretch", spacing=2)
        self.cur = W.label("—", "strong")
        self.kind = W.Segmented()
        for i, (text, icon) in enumerate(KINDS):
            self.kind.add(text, i, icon=icon)
        self.kind.setStyleSheet("QToolButton { padding: 0 7px; }")
        self.kind.changed.connect(self._kind_changed)
        self.stack = QStackedWidget()
        self.stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.stack.setFixedHeight(34)
        # 0 tecla
        self.key_combo = hid_combo()
        self.key_combo.setFixedWidth(200)
        self.b_capture = W.button("Capturar", "ghost", "teclado", on_click=self.start_capture,
                                  tip="Pulsa la tecla que quieres asignar")
        self.stack.addWidget(self._row("Tecla", self.key_combo, self.b_capture))
        # 1 combinación
        self.combo_keys = [hid_combo(allow_none=True) for _ in range(3)]
        items = []
        for i, c in enumerate(self.combo_keys):
            c.setFixedWidth(130)
            if i:
                items.append(W.label("+", "body2"))
            items.append(c)
        self.stack.addWidget(self._row("Teclas", *items))
        # 2 multimedia
        self.func_combo = QComboBox()
        self.func_combo.setMaxVisibleItems(14)
        for _key, lab, raw in FUNCTIONS:
            self.func_combo.addItem(lab, raw)
        self.func_combo.setFixedWidth(260)
        self.stack.addWidget(self._row("Función", self.func_combo))
        # 3 ratón
        self.mouse_combo = QComboBox()
        for _key, lab, raw in MOUSE:
            self.mouse_combo.addItem(lab, raw)
        self.mouse_combo.setFixedWidth(200)
        self.stack.addWidget(self._row("Botón", self.mouse_combo))
        # 4 macro
        self.macro_idx = W.Stepper(0, 49, 0, width=40)
        self.macro_mode = W.Segmented()
        for lab, code, tip in MACRO_MODES:
            self.macro_mode.add(lab, code, tip=tip)
        self.b_edit_macro = W.button("Editar", "link", on_click=self._edit_macro)
        self.b_edit_macro.setToolTip("Abrir esta macro en la sección Macros")
        self.stack.addWidget(self._row("Macro", self.macro_idx, self.macro_mode, self.b_edit_macro))
        # 5 desactivada / 6 por defecto
        self.stack.addWidget(self._row("", W.label("La tecla no hará nada al pulsarla.", "body2")))
        self.default_lbl = W.label("", "body2")
        self.stack.addWidget(self._row("", self.default_lbl))
        for c in [self.key_combo, *self.combo_keys, self.func_combo, self.mouse_combo]:
            c.currentIndexChanged.connect(self._dirty)
            if c.isEditable():
                c.editTextChanged.connect(self._dirty)
        self.macro_idx.valueChanged.connect(self._dirty)
        self.macro_mode.changed.connect(self._dirty)

        self.b_restore = W.button("Restaurar esta tecla", "ghost", on_click=self.restore_key)
        self.b_apply = W.button("Aplicar", "primary", "aplicar", on_click=self.apply)
        grid = W.vbox(spacing=12)
        grid.addLayout(W.hbox(self._lbl("Acción actual"), self.cur, "stretch", spacing=12))
        grid.addLayout(W.hbox(self._lbl("Tipo"), "stretch", spacing=12))
        grid.addWidget(self.kind)
        grid.addWidget(self.stack)
        grid.addLayout(W.hbox("stretch", self.b_restore, self.b_apply, spacing=8))
        row = W.hbox(left, 20, W.divider("v"), 20, spacing=0)
        row.addLayout(grid, 1)
        pl.addLayout(row)
        self.panel = panel
        self.lay.addWidget(panel)
        self.lay.addStretch(1)
        self._update_header()
        self._set_editor_enabled(False)

    # ------------------------------------------------------------ helpers
    def _lbl(self, text):
        lb = W.label(text, "body2")
        lb.setFixedWidth(100)
        return lb

    def _row(self, title, *widgets):
        w = QWidget()
        lay = W.hbox(spacing=8, parent=w)
        if title:
            lay.addWidget(self._lbl(title))
        for x in widgets:
            lay.addWidget(x)
        lay.addStretch(1)
        return w

    def resizeEvent(self, e):
        super().resizeEvent(e)
        narrow = self.width() < 1000
        for b in self.kind.buttons:
            b.setToolButtonStyle(Qt.ToolButtonTextOnly if narrow else Qt.ToolButtonTextBesideIcon)

    def _update_header(self):
        self.header.subtitle.setText("Haz clic en una tecla para cambiar lo que hace. "
                                     f"Se guarda en el perfil {self.win.profile + 1}.")

    def _set_editor_enabled(self, on: bool):
        for w in (self.kind, self.stack, self.b_restore):
            w.setEnabled(on)
        if not on:
            W.disable_with_reason(self.b_apply, "Elige una tecla primero")

    # ------------------------------------------------------------ carga
    def on_connected(self):
        self._update_header()
        self.load()

    def on_profile(self):
        self._update_header()
        self.load()

    def _layer_changed(self, fn):
        self.fn = bool(fn)
        self.sel_layer.setText("Capa Fn (Fn + tecla)" if self.fn else "Capa normal")
        self.kind.buttons[6].setEnabled(not self.fn)
        self.kind.buttons[6].setToolTip("La capa Fn no tiene valores por defecto" if self.fn else "")
        W.disable_with_reason(self.b_reset, "Solo en la capa normal" if self.fn else None)
        self.hint.setText("Lo que hace cada tecla mientras mantienes Fn." if self.fn
                          else "Lo que hace cada tecla al pulsarla.")
        self.load()

    def load(self):
        if not self.kb:
            return
        self.win.run(self.kb.read_matrix, on_done=self._loaded, progress=True, fn=self.fn,
                     label="Leyendo teclas…", retry=self.load,
                     count_fmt=lambda f, m: f"{round(f * 8)}/8")

    def _loaded(self, actions):
        self.actions = actions
        self.refresh()
        self.win.pages["macros"].refresh_assignments()

    def refresh(self):
        labels = {}
        locked = set()
        n_remap = n_off = n_sys = 0
        fnk = next((k for k in KEYS if k.default_action.raw == (10, 1, 0, 0)), None)
        lock_tip = "Tecla del sistema: no se puede cambiar"
        for k in KEYS:
            if k.slot >= len(self.actions):
                continue
            a = self.actions[k.slot]
            legend, icon = legend_for(a)
            name = f"Fn + {k.name}" if self.fn else k.name
            if fnk and k.slot == fnk.slot:
                locked.add(k.slot)
                labels[k.slot] = (KeyLabel("Fn", cls="held", tip="Fn · mantenla para usar esta capa") if self.fn
                                  else KeyLabel("Fn", cls="locked", tip=f"Fn · {lock_tip}"))
            elif self.fn and is_system(a.raw):
                locked.add(k.slot)
                labels[k.slot] = KeyLabel(legend, sub=k.name, cls="locked", icon=icon,
                                          tip=f"{name} → {a.describe()}\n{lock_tip}")
                n_sys += 1
            elif self.fn:
                if a.raw == (0, 0, 0, 0):
                    labels[k.slot] = KeyLabel(k.name, cls="dim", tip=f"{name} · sin función")
                else:
                    labels[k.slot] = KeyLabel(legend, sub=k.name, cls="remap", icon=icon,
                                              tip=f"{name} → {a.describe()}")
                    n_remap += 1
            elif a != k.default_action:
                if a.kind == "off":
                    labels[k.slot] = KeyLabel("", sub=k.name, cls="off", icon="desactivada",
                                              tip=f"{k.name} · desactivada")
                    n_off += 1
                else:
                    labels[k.slot] = KeyLabel(legend, sub=k.name, cls="remap", icon=icon,
                                              tip=f"{k.name} → {a.describe()}")
                    n_remap += 1
            else:
                labels[k.slot] = KeyLabel(k.name, tip=f"{k.name} · {a.describe()}")
        self.kbv.labels = labels
        self.kbv.locked = locked
        self.kbv.update()
        if self.fn:
            self.n_remap.setText(f"{n_remap} con función")
            self.n_off.setText(f"{n_sys} del sistema")
            self.mk_off.kind = "locked"
        else:
            self.n_remap.setText(f"{n_remap} reasignada" + ("s" if n_remap != 1 else ""))
            self.n_off.setText(f"{n_off} desactivada" + ("s" if n_off != 1 else ""))
            self.mk_off.kind = "off"
        self.mk_off.update()
        if self.selected and self.selected.slot in locked:
            self.selected = None
            self.kbv.selected = None
            self.preview.set(None, None)
            self.sel_name.setText("Elige una tecla")
            self.cur.setText("—")
            self._set_editor_enabled(False)
        elif self.selected:
            self.select_key(self.selected)

    def locked_clicked(self, k: PhysicalKey):
        a = self.actions[k.slot] if k.slot < len(self.actions) else None
        name = f"Fn + {k.name}" if self.fn else k.name
        what = "Fn" if (a and a.raw == (10, 1, 0, 0)) else (a.describe() if a else k.name)
        self.win.toast("warn", f"{name}: {what}. Es una tecla del sistema y no se puede cambiar.")

    # ------------------------------------------------------------ selección
    def select_key(self, k: PhysicalKey):
        self.selected = k
        self.kbv.selected = k.slot
        self.kbv.update()
        self.sel_name.setText(k.name)
        cur = self.actions[k.slot] if k.slot < len(self.actions) else None
        self.preview.set(k, self.kbv.labels.get(k.slot))
        self.cur.setText(cur.describe() if cur else "—")
        self._set_editor_enabled(True)
        self.default_lbl.setText(f"Vuelve a su función de fábrica: {k.default_action.describe()}.")
        if cur:
            self._show_action(cur)
        self._dirty()

    def _show_action(self, a: Action):
        widgets = [self.key_combo, *self.combo_keys, self.func_combo, self.mouse_combo]
        for w in widgets:
            w.blockSignals(True)
        t, x, y, z = a.raw
        kind = a.kind
        idx = KIND_INDEX.get(kind, 0)
        if kind == "key":
            self.key_combo.setCurrentIndex(max(0, self.key_combo.findData(y)))
        elif kind == "combo":
            for c, v in zip(self.combo_keys, (x, y, z)):
                c.setCurrentIndex(max(0, c.findData(v)))
        elif kind in ("function", "media"):
            i = self.func_combo.findData(a.raw)
            if i >= 0:
                self.func_combo.setCurrentIndex(i)
        elif kind == "mouse":
            i = self.mouse_combo.findData(a.raw)
            if i >= 0:
                self.mouse_combo.setCurrentIndex(i)
        elif kind == "macro":
            self.macro_idx.setValue(y, emit=False)
            self.macro_mode.setValue(x)
        for w in widgets:
            w.blockSignals(False)
        self.kind.setIndex(idx)
        self.stack.setCurrentIndex(idx)

    def _kind_changed(self, i):
        self.stack.setCurrentIndex(i)
        self._dirty()

    def _dirty(self, *_a):
        if not self.selected:
            return
        try:
            act = self.build_action()
        except (ValueError, TypeError):
            W.disable_with_reason(self.b_apply, "La acción no es válida")
            return
        cur = self.actions[self.selected.slot] if self.selected.slot < len(self.actions) else None
        W.disable_with_reason(self.b_apply, None if act != cur else "No hay cambios que aplicar")
        is_default = cur == self.selected.default_action
        W.disable_with_reason(self.b_restore, "Solo en la capa normal" if self.fn else
                              ("Ya tiene su función de fábrica" if is_default else None))

    def build_action(self) -> Action:
        i = self.kind.index()
        if i == 0:
            return Action.key(combo_value(self.key_combo))
        if i == 1:
            codes = [combo_value(c) for c in self.combo_keys]
            return Action.combo([c for c in codes if c])
        if i == 2:
            return Action(tuple(self.func_combo.currentData()))
        if i == 3:
            return Action(tuple(self.mouse_combo.currentData()))
        if i == 4:
            return Action.macro(self.macro_idx.value(), self.macro_mode.value())
        if i == 5:
            return Action.disabled()
        return self.selected.default_action

    # ------------------------------------------------------------ captura
    def start_capture(self):
        self.capturing = True
        self.b_capture.setText("Pulsa una tecla…")
        W.set_variant(self.b_capture, "secondary")
        self.grabKeyboard()

    def keyPressEvent(self, e):
        if self.capturing:
            code = qt_to_hid(e)
            self.releaseKeyboard()
            self.capturing = False
            self.b_capture.setText("Capturar")
            W.set_variant(self.b_capture, "ghost")
            if code:
                self.key_combo.setCurrentIndex(max(0, self.key_combo.findData(code)))
                self._dirty()
            else:
                self.win.toast("warn", "Esa tecla no tiene código HID equivalente.")
            return
        super().keyPressEvent(e)

    # ------------------------------------------------------------ aplicar
    def apply(self, act: Action | None = None):
        if not self.kb or not self.selected:
            return
        try:
            act = act or self.build_action()
        except ValueError as e:
            self.win.toast("err", str(e))
            return
        k = self.selected
        fn = self.fn

        def done(_):
            if k.slot < len(self.actions):
                self.actions[k.slot] = act
            self.refresh()
            name = f"Fn + {k.name}" if fn else k.name
            self.win.toast("ok", f"{name} → {act.describe()}")
            self.win.pages["macros"].refresh_assignments()

        self.win.run(self.kb.set_key, k, act, fn=fn, on_done=done, label=f"Asignando {k.name}…",
                     retry=lambda: self.apply(act))

    def restore_key(self):
        if self.selected:
            self.apply(self.selected.default_action)

    def reset_all(self):
        if not self.kb or self.fn:
            return

        def work():
            for k in KEYS:
                if k.slot < len(self.actions) and self.actions[k.slot] != k.default_action:
                    self.kb.set_key(k, k.default_action)

        def done(_):
            self.win.toast("ok", "Todas las teclas vuelven a su función de fábrica")
            self.load()

        self.win.confirm("¿Restaurar todas las teclas?",
                         f"Todas las teclas de la capa normal del perfil {self.win.profile + 1} volverán a su "
                         "función de fábrica. Las macros no cambian.",
                         "Restaurar todas", lambda: self.win.run(work, on_done=done, label="Restaurando teclas…"),
                         danger=True, icon="restaurar")

    def _edit_macro(self):
        self.win.go("macros")
        self.win.pages["macros"].select(self.macro_idx.value())

