"""Sección Macros: lista de 50 posiciones y editor visual de secuencias."""

from __future__ import annotations

import time

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QFrame, QLabel, QListWidget, QListWidgetItem, QMenu,
                               QPlainTextEdit, QScrollArea, QSizePolicy, QStackedWidget, QWidget)

from ... import protocol as P
from ...keymap import KEYS
from ...macros import MOUSE_CODES, Macro, MacroEvent, encoded_length, parse_macro_text
from .. import widgets as W
from ...i18n import t as tr
from ..hidkeys import qt_to_hid
from ..window import Page
from .common import hid_combo, key_display

MODS = {0xE0: "Ctrl", 0xE1: "Shift", 0xE2: "Alt", 0xE3: "Win", 0xE4: "RCtrl", 0xE5: "RShift", 0xE6: "RAlt",
        0xE7: "RWin"}
MOUSE_LABELS = {"left": "Left click", "right": "Right click", "middle": "Middle click", "forward": "Forward",
                "back": "Back", "wheelleft": "Wheel left", "wheelright": "Wheel right",
                "wheelforward": "Wheel up", "wheelback": "Wheel down"}
MOUSE_BY_CODE = {v: k for k, v in MOUSE_CODES.items()}


def summarize(m: Macro) -> str:
    """«Ctrl+C, 80 ms, Ctrl+V» a partir de los eventos."""
    toks: list[str] = []
    held: list[int] = []
    for e in m.events:
        if e.type == "delay":
            toks.append(f"{e.value} ms")
        elif e.type == "mouse" and e.down:
            lab = MOUSE_LABELS.get(MOUSE_BY_CODE.get(e.value, ""))
            toks.append(tr(lab) if lab else tr("Click"))
        elif e.type == "key":
            if e.down:
                if e.value in MODS:
                    held.append(e.value)
                else:
                    toks.append("+".join([MODS[h] for h in held] + [key_display(e.value)]))
            elif e.value in held:
                if toks and not any(MODS[e.value] in t for t in toks[-1:]):
                    toks.append("+".join(MODS[h] for h in held))
                held.remove(e.value)
    s = ", ".join(toks) or "—"
    if m.repeat > 1:
        s += f" ×{m.repeat}"
    return s


class MacroItem(QFrame):
    def __init__(self, idx: int, page: "MacrosPage"):
        super().__init__()
        self.idx, self.page = idx, page
        self.setProperty("macroitem", "")
        self.setCursor(Qt.PointingHandCursor)
        self.num = QLabel(f"{idx:02d}")
        self.num.setProperty("mlidx", "")
        self.title = W.label(tr("Empty"))
        self.title.setProperty("mlt", "empty")
        self.meta = W.label("", "cap")
        self.meta.hide()
        for lb in (self.title, self.meta):
            lb.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        lay = W.hbox(self.num, spacing=10, margins=(10, 7, 10, 7), parent=self)
        lay.addLayout(W.vbox(self.title, self.meta, spacing=0), 1)

    def set(self, m: Macro | None, assigned: str = ""):
        used = bool(m and m.events)
        W.set_prop(self.num, "mlidx", "used" if used else "")
        W.set_prop(self.title, "mlt", "used" if used else "empty")
        if used:
            self.title.setText(summarize(m))
            n = len(m.events)
            meta = (tr("{n} events") if n != 1 else tr("{n} event")).format(n=n) + f" · {encoded_length(m.events)} B"
            if assigned:
                meta += f" · {assigned}"
            self.meta.setText(meta)
        else:
            self.title.setText(tr("Empty") if m is not None else "…")
        self.meta.setVisible(used)

    def set_on(self, on: bool):
        W.set_prop(self, "macroitem", "on" if on else "")

    def mousePressEvent(self, e):
        self.page.select(self.idx)


class EventRow(QFrame):
    ICONS = {"down": "pulsar", "up": "soltar", "wait": "esperar", "mouse": "raton"}
    COLORS = {"down": "accent", "up": "text-2", "wait": "warning", "mouse": "success"}

    def __init__(self, page: "MacrosPage", ev: MacroEvent, n: int, depth: int):
        super().__init__()
        self.page, self.ev = page, ev
        self.setProperty("ev", True)
        lay = W.hbox(spacing=8, margins=(4, 4, 8, 4), parent=self)
        grip = W.icon_label("arrastrar", "text-3", 16)
        grip.setCursor(Qt.OpenHandCursor)
        grip.setToolTip(tr("Drag to reorder"))
        num = W.label(str(n), "mono2")
        num.setStyleSheet("font-size: 11px;")
        num.setFixedWidth(20)
        num.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        lay.addWidget(grip)
        lay.addWidget(num)
        for _ in range(depth):
            g = QFrame()
            g.setProperty("evguide", True)
            g.setFixedWidth(16)
            lay.addSpacing(6)
            lay.addWidget(g)
        kind = "wait" if ev.type == "delay" else ("mouse" if ev.type in ("mouse", "move") else
                                                  ("down" if ev.down else "up"))
        box = QFrame()
        box.setProperty("evic", kind)
        W.hbox(W.icon_label(self.ICONS[kind], self.COLORS[kind], 14), margins=(6, 6, 6, 6), parent=box)
        lay.addWidget(box)
        if ev.type == "delay":
            text = tr("Wait")
        elif ev.type == "mouse":
            text = tr("Click") if ev.down else tr("Release click")
        elif ev.type == "move":
            text = tr("Move mouse")
        else:
            text = tr("Press") if ev.down else tr("Release")
        t = W.label(text, "body2")
        t.setMinimumWidth(56)
        lay.addWidget(t)
        if ev.type == "delay":
            st = W.Stepper(0, 65535, ev.value, "ms", buttons=False, width=44)
            st.setFixedHeight(28)
            st.valueChanged.connect(self._delay)
            lay.addWidget(st)
        elif ev.type == "key":
            c = hid_combo()
            c.setProperty("kbd", True)
            c.setCurrentIndex(max(0, c.findData(ev.value)))
            c.setSizeAdjustPolicy(QComboBox.AdjustToContents)
            c.currentIndexChanged.connect(lambda _i, c=c: self._key(c))
            lay.addWidget(c)
        elif ev.type == "mouse":
            c = QComboBox()
            for name, code in MOUSE_CODES.items():
                c.addItem(tr(MOUSE_LABELS[name]) if name in MOUSE_LABELS else name, code)
            c.setCurrentIndex(max(0, c.findData(ev.value)))
            c.currentIndexChanged.connect(lambda _i, c=c: self._mouse(c))
            lay.addWidget(c)
        else:
            lay.addWidget(W.label(f"({ev.dx}, {ev.dy})", "mono2"))
        lay.addStretch(1)
        lay.addWidget(W.button("", "ghost", "cerrar", size="sm", tip=tr("Remove event"),
                               on_click=lambda: page.remove_event(self.ev)))

    def _delay(self, v):
        self.ev.value = v
        self.page.events_changed(rebuild=False)

    def _key(self, c):
        if c.currentData() is not None:
            self.ev.value = c.currentData()
            self.page.events_changed(rebuild=True)

    def _mouse(self, c):
        self.ev.value = c.currentData()
        self.page.events_changed(rebuild=True)


class EventList(QListWidget):
    def __init__(self, page):
        super().__init__()
        self.page = page
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setSpacing(1)
        self.model().rowsMoved.connect(lambda *_: QTimer.singleShot(0, page.reordered))


class MacrosPage(Page):
    def __init__(self, win):
        super().__init__(win, scroll=False)
        self.macros: list[Macro | None] = [None] * P.MACRO_MAX
        self.loaded = False
        self.idx = 0
        self.events: list[MacroEvent] = []
        self.repeat = 1
        self.saved: str | None = None
        self.recording = False
        self.last_t = 0.0
        self.filter = "all"

        self.lay.addWidget(W.PageHeader(tr("Macros"), tr("Sequences of keys and clicks that you then assign to any "
                                                        "key. The keyboard stores 50.")))
        # --- lista
        left, ll = W.card(padding=(12, 14, 12, 8), spacing=10)
        left.setFixedWidth(288)
        self.left_card = left
        self.used_lbl = W.label("", "cap")
        ll.addLayout(W.hbox(5, W.label(tr("Slots"), "sub"), "stretch", self.used_lbl, 5))
        self.filt = W.Segmented([(tr("All"), "all"), (tr("Used"), "used"), (tr("Empty slots"), "empty")], block=True)
        self.filt.changed.connect(self._filter)
        ll.addWidget(self.filt)
        self.items = [MacroItem(i, self) for i in range(P.MACRO_MAX)]
        host = QWidget()
        hl = W.vbox(*self.items, "stretch", spacing=2, parent=host)
        hl.setContentsMargins(0, 0, 4, 0)
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setFrameShape(QFrame.NoFrame)
        sa.setWidget(host)
        self.list_scroll = sa
        ll.addWidget(sa, 1)

        # --- editor
        right, rl = W.card(padding=(18, 16, 18, 16), spacing=12)
        self.title = W.label("Macro 00", "title")
        self.state = W.pill(tr("Empty"), "neutral")
        self.assign = W.label("", "cap", rich=True)
        self.assign.linkActivated.connect(lambda _l: self.win.go("keys"))
        self.view = W.Segmented()
        self.view.add(tr("Visual"), "visual", icon="macros")
        self.view.add(tr("Text"), "text", icon="codigo")
        self.view.changed.connect(self._view)
        head = W.hbox(W.vbox(W.hbox(self.title, self.state, "stretch", spacing=10), self.assign, spacing=2), "stretch",
                      self.view, spacing=12)
        rl.addLayout(head)
        self.b_rec = W.button(tr("Record"), "secondary", "grabar", on_click=self.toggle_record)
        W.set_icon(self.b_rec, "grabar", "error", 16)
        self.b_add = W.button(tr("Add event"), "secondary", "mas")
        menu = QMenu(self)
        for text, icon, kind in (("Press key", "pulsar", "down"), ("Release key", "soltar", "up"),
                                 ("Press and release", "teclas", "tap"), ("Wait", "esperar", "delay"),
                                 ("Mouse click", "raton", "click")):
            a = menu.addAction(W.theme().icon(icon, "text-2", 16), tr(text))
            a.triggered.connect(lambda _=False, k=kind: self.add_event(k))
        self.b_add.setMenu(menu)
        self.rec_waits = W.Switch(True)
        self.drag_hint = W.label(tr("Drag  ⠿  to reorder"), "cap")
        self.tools = W.hbox(self.b_rec, self.b_add, 6, self.rec_waits, W.label(tr("Record delays"), "strong"), "stretch",
                            self.drag_hint, spacing=8)
        rl.addLayout(self.tools)
        self.stack = QStackedWidget()
        self.list = EventList(self)
        self.empty_hint = W.label(tr("No events. Press «Record» and type, or add events by hand."), "cap")
        self.empty_hint.setAlignment(Qt.AlignCenter)
        vis = QWidget()
        W.vbox(self.list, self.empty_hint, spacing=0, parent=vis)
        self.stack.addWidget(vis)
        self.text = QPlainTextEdit()
        self.text.setPlaceholderText("down:ctrl, tap:c, up:ctrl, delay:50, tap:enter")
        self.text.textChanged.connect(self._text_changed)
        self.text_hint = W.label("<code>down:</code>" + tr("press") + " · <code>up:</code>" + tr("release") +
                                 " · <code>tap:</code>" + tr("press and release") + " · <code>delay:</code>ms · "
                                 "<code>down:mouse-left</code> " + tr("mouse"), "cap", rich=True)
        tw = QWidget()
        W.vbox(self.text, self.text_hint, spacing=8, parent=tw)
        self.stack.addWidget(tw)
        rl.addWidget(self.stack, 1)
        rl.addWidget(W.divider())
        self.rep = W.Stepper(1, 65535, 1, width=46)
        self.rep.valueChanged.connect(self._rep)
        self.cap_meter = W.Meter(190)
        self.cap_lbl = W.label("", "mono2")
        foot = W.hbox(W.label(tr("Repeats"), "strong"), self.rep, 16,
                      W.vbox(W.hbox(W.label(tr("Capacity"), "cap"), "stretch", self.cap_lbl, spacing=8), self.cap_meter,
                             spacing=4), "stretch", spacing=10)
        rl.addLayout(foot)
        self.b_read = W.button(tr("Read from keyboard"), "ghost", "leer", on_click=self.read)
        self.b_clear = W.button(tr("Delete"), "danger", "borrar", on_click=self.clear)
        self.b_save = W.button(tr("Save to keyboard"), "primary", "guardar", on_click=self.save)
        rl.addLayout(W.hbox("stretch", self.b_read, self.b_clear, self.b_save, spacing=8))

        row = W.hbox(spacing=16)
        row.addWidget(left)
        row.addWidget(right, 1)
        self.lay.addLayout(row, 1)
        self._render()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        narrow = self.width() < 1000
        self.drag_hint.setVisible(not narrow)
        self.left_card.setFixedWidth(250 if narrow else 288)

    # ------------------------------------------------------------ carga
    def on_connected(self):
        self.loaded = False
        self.macros = [None] * P.MACRO_MAX
        for it in self.items:
            it.set(None)
        if self.isVisible():
            self.load_all()

    def on_shown(self):
        if not self.loaded:
            self.load_all()

    def showEvent(self, e):
        super().showEvent(e)
        if self.kb and not self.loaded:
            QTimer.singleShot(0, self.load_all)

    def load_all(self):
        kb = self.kb
        if not kb or self.loaded:
            return
        self.loaded = True

        def work(progress):
            out = []
            for i in range(P.MACRO_MAX):
                out.append(kb.read_macro(i))
                progress((i + 1) / P.MACRO_MAX, "")
            return out

        def done(ms):
            self.macros = ms
            self.refresh_assignments()
            self.select(self.idx, force=True)

        def fail(_m):
            self.loaded = False

        self.win.run(work, progress=True, on_done=done, on_error=fail, label=tr("Reading macros…"),
                     count_fmt=lambda f, m: f"{round(f * P.MACRO_MAX)}/{P.MACRO_MAX}", retry=self.load_all)

    def assignments(self) -> dict[int, list[str]]:
        keys = getattr(self.win, "pages", {}).get("keys")
        out: dict[int, list[str]] = {}
        if keys is None:
            return out
        for k in KEYS:
            if k.slot < len(keys.actions):
                a = keys.actions[k.slot]
                if a.kind == "macro":
                    out.setdefault(a.raw[2], []).append(("Fn + " if keys.fn else "") + k.name)
        return out

    def refresh_assignments(self):
        asg = self.assignments()
        used = 0
        for i, it in enumerate(self.items):
            m = self.macros[i]
            it.set(m, ", ".join(asg.get(i, [])))
            used += bool(m and m.events)
        self.used_lbl.setText(tr("{n} of {max} used").format(n=used, max=P.MACRO_MAX))
        self._filter(self.filt.value())
        self._header()

    def _filter(self, f):
        self.filter = f
        for i, it in enumerate(self.items):
            m = self.macros[i]
            used = bool(m and m.events)
            it.setVisible(f == "all" or (f == "used") == used)

    # ------------------------------------------------------------ selección
    def select(self, idx: int, force: bool = False):
        if idx == self.idx and not force:
            return
        if self.dirty() and not force:
            self.win.confirm(tr("Discard the changes to macro {n}?").format(n=f"{self.idx:02d}"),
                             tr("You have changes not saved to the keyboard."), tr("Discard"),
                             lambda: self.select(idx, force=True), danger=True, icon="aviso")
            return
        self.stop_record()
        self.idx = idx
        for it in self.items:
            it.set_on(it.idx == idx)
        self.list_scroll.ensureWidgetVisible(self.items[idx])
        m = self.macros[idx] or Macro([], 1)
        self.events = [MacroEvent(e.type, e.value, e.down, e.dx, e.dy) for e in m.events]
        self.repeat = max(1, m.repeat)
        self.saved = self._snapshot()
        self.rep.setValue(self.repeat, emit=False)
        self._render()

    def _snapshot(self) -> str:
        return Macro(self.events, self.repeat).to_text() + f"|{self.repeat}"

    def dirty(self) -> bool:
        return self.saved is not None and self._snapshot() != self.saved

    def _header(self):
        self.title.setText(f"Macro {self.idx:02d}")
        asg = self.assignments().get(self.idx)
        if asg:
            self.assign.setText(tr("Assigned to <b>{keys}</b> in profile {n}.").format(keys=", ".join(asg),
                                                                                     n=self.win.profile + 1))
        else:
            acc = W.theme().hex("accent")
            self.assign.setText(tr("Not assigned. Assign it to a key in the Keys section.") + " "
                                f"<a href='keys' style='color:{acc};text-decoration:none'>{tr('Go to Keys')} ›</a>")
        if self.dirty():
            self.state.setText(tr("Not saved"))
            W.set_prop(self.state, "pill", "warn")
        elif self.events:
            self.state.setText(tr("Saved"))
            W.set_prop(self.state, "pill", "ok")
        else:
            self.state.setText(tr("Empty"))
            W.set_prop(self.state, "pill", "neutral")

    # ------------------------------------------------------------ editor
    def _render(self):
        self.list.clear()
        depth_keys: list[int] = []
        for n, ev in enumerate(self.events, 1):
            if ev.type == "key" and not ev.down and ev.value in depth_keys:
                depth_keys.remove(ev.value)
            depth = min(len(depth_keys), 4)
            row = EventRow(self, ev, n, depth)
            it = QListWidgetItem()
            it.setData(Qt.UserRole, id(ev))
            it.setSizeHint(QSize(100, 42))
            self.list.addItem(it)
            self.list.setItemWidget(it, row)
            if ev.type == "key" and ev.down:
                depth_keys.append(ev.value)
        self.empty_hint.setVisible(not self.events)
        self.list.setVisible(bool(self.events))
        if self.view.value() == "text":
            self.text.blockSignals(True)
            self.text.setPlainText(Macro(self.events).to_text())
            self.text.blockSignals(False)
        self._update_cap()

    def _update_cap(self):
        n = encoded_length(self.events)
        lim = P.MACRO_MAX_BYTES
        tone = "error" if n > lim else ("warning" if n > lim * 0.85 else "accent")
        self.cap_meter.set(n / lim, tone)
        self.cap_lbl.setText(f"{n} / {lim} bytes")
        self.cap_lbl.setProperty("tone", {"error": "error", "warning": "warning"}.get(tone))
        W.repolish(self.cap_lbl)
        if not self.kb:
            reason = tr("Connect the keyboard")
        elif n > lim:
            reason = tr("{n} bytes too long: remove events or delays").format(n=n - lim)
        elif not self.dirty():
            reason = tr("No changes to save")
        else:
            reason = None
        W.disable_with_reason(self.b_save, reason)
        has = bool(self.events) or bool(self.macros[self.idx] and self.macros[self.idx].events)
        W.disable_with_reason(self.b_clear, None if has else tr("The macro is already empty"))
        self._header()

    def events_changed(self, rebuild: bool = True):
        if rebuild:
            QTimer.singleShot(0, self._render)
        else:
            self._update_cap()

    def reordered(self):
        by_id = {id(e): e for e in self.events}
        order = [self.list.item(i).data(Qt.UserRole) for i in range(self.list.count())]
        self.events = [by_id[i] for i in order if i in by_id]
        self._render()

    def remove_event(self, ev):
        self.events = [e for e in self.events if e is not ev]
        QTimer.singleShot(0, self._render)

    def add_event(self, kind: str):
        last_key = next((e.value for e in reversed(self.events) if e.type == "key"), 0x04)
        if kind == "down":
            self.events.append(MacroEvent("key", last_key, True))
        elif kind == "up":
            self.events.append(MacroEvent("key", last_key, False))
        elif kind == "tap":
            self.events += [MacroEvent("key", last_key, True), MacroEvent("key", last_key, False)]
        elif kind == "delay":
            self.events.append(MacroEvent("delay", 50))
        elif kind == "click":
            self.events += [MacroEvent("mouse", MOUSE_CODES["left"], True),
                            MacroEvent("mouse", MOUSE_CODES["left"], False)]
        self._render()
        self.list.scrollToBottom()

    def _rep(self, v):
        self.repeat = v
        self._update_cap()

    def _view(self, v):
        if v == "text":
            self.text.blockSignals(True)
            self.text.setPlainText(Macro(self.events).to_text())
            self.text.blockSignals(False)
            self.stack.setCurrentIndex(1)
        else:
            try:
                self.events = parse_macro_text(self.text.toPlainText())
            except (ValueError, KeyError) as e:
                self.view.setValue("text")
                self.win.toast("err", tr("I do not understand the text: {error}").format(error=e))
                return
            self.stack.setCurrentIndex(0)
            self._render()
        for w in (self.b_rec, self.b_add):
            W.disable_with_reason(w, tr("Only in the Visual view") if v == "text" else None)

    def _text_changed(self):
        try:
            self.events = parse_macro_text(self.text.toPlainText())
            W.set_prop(self.text, "error", False)
            self._update_cap()
        except (ValueError, KeyError):
            W.set_prop(self.text, "error", True)
            W.disable_with_reason(self.b_save, tr("Fix the macro text"))

    # ------------------------------------------------------------ grabar
    def toggle_record(self):
        if self.recording:
            self.stop_record()
        else:
            self.recording = True
            self.last_t = 0.0
            self.b_rec.setText(tr("Stop"))
            W.set_variant(self.b_rec, "rec-on")
            W.set_icon(self.b_rec, "detener", "error", 16)
            self.setFocus()
            self.grabKeyboard()
            self.win.toast("info", tr("Recording: type the sequence and press «Stop»."))

    def stop_record(self):
        if not self.recording:
            return
        self.recording = False
        self.releaseKeyboard()
        self.b_rec.setText(tr("Record"))
        W.set_variant(self.b_rec, "secondary")
        W.set_icon(self.b_rec, "grabar", "error", 16)

    def _record(self, e, down: bool):
        if e.isAutoRepeat():
            return
        code = qt_to_hid(e)
        if code is None:
            return
        now = time.monotonic()
        if self.rec_waits.isChecked() and self.last_t:
            ms = round((now - self.last_t) * 1000)
            if ms >= 10:
                self.events.append(MacroEvent("delay", min(ms, 65535)))
        self.last_t = now
        self.events.append(MacroEvent("key", code, down))
        self._render()
        self.list.scrollToBottom()

    def keyPressEvent(self, e):
        if self.recording:
            self._record(e, True)
            return
        super().keyPressEvent(e)

    def keyReleaseEvent(self, e):
        if self.recording:
            self._record(e, False)
            return
        super().keyReleaseEvent(e)

    # ------------------------------------------------------------ teclado
    def read(self):
        if not self.kb:
            return
        idx = self.idx

        def done(m):
            self.macros[idx] = m
            self.refresh_assignments()
            self.select(idx, force=True)

        self.win.run(self.kb.read_macro, idx, on_done=done, label=tr("Reading macro {n}…").format(n=f"{idx:02d}"), retry=self.read)

    def save(self):
        if not self.kb:
            return
        self.stop_record()
        idx = self.idx
        m = Macro([MacroEvent(e.type, e.value, e.down, e.dx, e.dy) for e in self.events], self.repeat)
        if encoded_length(m.events) > P.MACRO_MAX_BYTES:
            self.win.toast("err", tr("The macro is too long."))
            return

        def done(_):
            self.macros[idx] = m
            self.saved = self._snapshot() if idx == self.idx else self.saved
            self.refresh_assignments()
            self._update_cap()
            self.win.toast("ok", tr("Macro {n} saved").format(n=f"{idx:02d}"))

        self.win.run(self.kb.write_macro, idx, m, on_done=done, label=tr("Saving macro {n}…").format(n=f"{idx:02d}"),
                     retry=self.save)

    def clear(self):
        if not self.kb:
            return
        idx = self.idx

        def go():
            def done(_):
                self.macros[idx] = Macro([], 0)
                self.refresh_assignments()
                self.select(idx, force=True)
                self.win.toast("ok", tr("Macro {n} deleted").format(n=f"{idx:02d}"))
            self.win.run(self.kb.write_macro, idx, Macro([], 0), on_done=done, label=tr("Deleting macro {n}…").format(n=f"{idx:02d}"))

        asg = self.assignments().get(idx)
        extra = (" " + tr("It is still assigned to {keys}: that key will do nothing.").format(keys=", ".join(asg))
                 if asg else "")
        self.win.confirm(tr("Delete macro {n}?").format(n=f"{idx:02d}"), tr("It is deleted from the keyboard.") + extra,
                         tr("Delete"), go, danger=True,
                         icon="borrar")

