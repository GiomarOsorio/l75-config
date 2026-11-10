"""Sección Colores por tecla: el teclado como lienzo para pintar."""

from __future__ import annotations

from PySide6.QtCore import Qt

from ...keymap import KEYS
from .. import widgets as W
from ...i18n import t as tr
from ..keyboard_view import KeyboardView
from ..window import Page
from .common import Deck, mode_name


class ColorsPage(Page):
    def __init__(self, win):
        super().__init__(win)
        self.color = 0xFFB020
        self.slot_colors: dict[int, int] = {}
        self.undo: list[dict[int, int]] = []

        header = W.PageHeader(tr("Per-key colours"),
                              tr("Paint each key with its colour. Every click is sent to the keyboard instantly."))
        header.add(W.button(tr("Read colours"), "secondary", "leer", on_click=self.load))
        self.b_all = header.add(W.button(tr("Paint all"), "secondary", "pintar-todas", on_click=self.paint_all))
        self.lay.addWidget(header)

        self.banner = W.Banner("info", "", tr("Turn on User picture mode"),
                               lambda: self.win.pages["light"].set_user_mode())
        self.banner.hide()
        self.lay.addWidget(self.banner)

        deck = Deck()
        self.brush = W.ColorButton(self.color, W.PAINT_SWATCHES)
        self.brush.colorChanged.connect(self.set_color)
        self.palette = W.SwatchRow(W.PAINT_SWATCHES, 22)
        self.palette.picked.connect(self.set_color)
        self.tool = W.Segmented()
        self.tool.add(tr("Brush"), "brush", icon="color", tip=tr("Brush: paints the key"))
        self.tool.add(tr("Eyedropper"), "pick", icon="cuentagotas", tip=tr("Eyedropper: takes the colour of a key"))
        self.tool.changed.connect(self._tool)
        self.b_undo = W.button(tr("Undo"), "ghost", "restaurar", size="sm", on_click=self.do_undo)
        W.disable_with_reason(self.b_undo, tr("Nothing to undo"))
        bar = W.hbox(W.label(tr("Brush"), "strong"), self.brush, self.palette, "stretch", self.tool, self.b_undo,
                     spacing=10)
        self.kbv = KeyboardView(mode="paint", deck=False)
        self.kbv.setMaximumWidth(920)
        self.kbv.keyPainted.connect(self.paint)
        self.kbv.strokeStarted.connect(lambda: setattr(self, "_stroke", False))
        hint = W.label(tr("Click or drag over the keys to paint  ·  Black = key off"), "cap")
        hint.setAlignment(Qt.AlignCenter)
        W.vbox(bar, 8, W.hbox("stretch", self.kbv, "stretch", spacing=0), hint, spacing=8, margins=(20, 16, 20, 18), parent=deck)
        self.lay.addWidget(deck)
        self.lay.addStretch(1)
        self.palette.select(self.color)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        narrow = self.width() < 1000
        for b in self.tool.buttons:
            b.setToolButtonStyle(Qt.ToolButtonIconOnly if narrow else Qt.ToolButtonTextBesideIcon)
        self.b_undo.setText("" if narrow else tr("Undo"))
        W.set_prop(self.b_undo, "icononly", narrow)

    # ------------------------------------------------------------ estado
    def light_changed(self, s):
        if s.mode == "user":
            self.banner.hide()
        else:
            name = mode_name(s.mode)
            self.banner.set_text(tr("The current lighting is <b>{name}</b>. These colours only show in "
                                    "<b>User picture</b> mode.").format(name=name))
            self.banner.show()

    def set_color(self, rgb: int):
        self.color = rgb
        self.brush.set_rgb(rgb)
        self.palette.select(rgb)
        if self.tool.value() == "pick":
            self.tool.setValue("brush")
            self._tool("brush")

    def _tool(self, v):
        self.kbv.picking = v == "pick"

    def _show(self):
        self.kbv.colors = dict(self.slot_colors)
        self.kbv.update()

    # ------------------------------------------------------------ teclado
    def on_connected(self):
        self.load()

    def load(self):
        if self.kb:
            self.win.run(self.kb.get_key_colors, on_done=self._loaded, label=tr("Reading colours…"), retry=self.load)

    def _loaded(self, colors):
        self.slot_colors = {k.slot: colors[k.slot] for k in KEYS}
        self.undo.clear()
        W.disable_with_reason(self.b_undo, tr("Nothing to undo"))
        self._show()

    def paint(self, k):
        if self.kbv.picking:
            self.set_color(self.slot_colors.get(k.slot, 0))
            return
        if not self.kb:
            return
        color = self.color
        old = self.slot_colors.get(k.slot, 0)
        if old == color:
            return
        self._push_undo({k.slot: old})
        self.slot_colors[k.slot] = color
        self._show()
        self.win.run(self.kb.set_key_color, k, color, label=tr("Colour {key}").format(key=k.name), quiet=True)

    def _push_undo(self, d):
        # agrupa los trazos seguidos en un solo paso cuando se arrastra
        if self.kbv._painting and self.undo and getattr(self, "_stroke", False):
            self.undo[-1].update({s: c for s, c in d.items() if s not in self.undo[-1]})
        else:
            self.undo.append(d)
            self.undo = self.undo[-50:]
        self._stroke = self.kbv._painting
        W.disable_with_reason(self.b_undo, None)

    def do_undo(self):
        if not self.undo or not self.kb:
            return
        step = self.undo.pop()
        kb = self.kb

        def work():
            for slot, c in step.items():
                kb.set_key_color(slot, c)

        self.slot_colors.update(step)
        self._show()
        self.win.run(work, label=tr("Undoing…"))
        if not self.undo:
            W.disable_with_reason(self.b_undo, tr("Nothing to undo"))

    def paint_all(self):
        if not self.kb:
            return
        color = self.color
        kb = self.kb
        self._push_undo(dict(self.slot_colors))
        self._stroke = False

        def work(progress):
            for i, k in enumerate(KEYS):
                kb.set_key_color(k, color)
                progress((i + 1) / len(KEYS), "pintando")

        for k in KEYS:
            self.slot_colors[k.slot] = color
        self._show()
        self.win.run(work, progress=True, label=tr("Painting all…"),
                     count_fmt=lambda f, m: f"{round(f * len(KEYS))}/{len(KEYS)}",
                     on_done=lambda _: self.win.toast("ok", tr("All keys set to #{rgb}").format(rgb=f"{color:06X}"), tr("Undo"),
                                                      self.do_undo))
