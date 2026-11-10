"""Sección Iluminación: tarjetas de efectos con vista previa y panel de ajustes."""

from __future__ import annotations

import time
from dataclasses import replace

from PySide6.QtCore import QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QPainter, QPen
from PySide6.QtWidgets import QAbstractButton, QGridLayout, QSizePolicy, QToolButton, QWidget

from ... import lighting as L
from .. import widgets as W
from ..effects import DEMO, paint_preview, paint_strip
from ..theme import font, theme
from ..window import Page
from .common import MODE_HINTS, MODE_NAMES, OPTION_ICONS, OPTION_NAMES, color_name


def _desc(s: L.LightSetting, side: bool) -> str:
    m = (L.SIDE_MODE_BY_KEY if side else L.MODE_BY_KEY).get(s.mode)
    parts = [MODE_NAMES.get(s.mode, s.mode)]
    if m and m.kind != "off":
        parts.append(f"brillo {s.brightness}")
        if m.color or m.kind == "music":
            parts.append("arcoíris" if s.rainbow else color_name(s.color))
    return " · ".join(parts)


class ModeCard(QAbstractButton):
    """Tarjeta de modo: vista previa (2,6:1) + nombre + punto «en el teclado»."""

    def __init__(self, mdef: L.ModeDef, side: bool, page: "LightPage"):
        super().__init__()
        self.m, self.side, self.page = mdef, side, page
        self.setCheckable(True)
        self.live = False
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumWidth(120)
        self.setToolTip(MODE_HINTS.get(mdef.key, ""))

    def heightForWidth(self, w):  # noqa: N802
        return round((w - 10) / 2.6) + 34

    def hasHeightForWidth(self):  # noqa: N802
        return True

    def sizeHint(self):
        return QSize(160, self.heightForWidth(160))

    def resizeEvent(self, e):
        self.setFixedHeight(self.heightForWidth(self.width()))

    def enterEvent(self, e):
        self.page.hovered = self
        self.update()

    def leaveEvent(self, e):
        if self.page.hovered is self:
            self.page.hovered = None
        self.update()

    def paintEvent(self, _e):
        t = theme()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        on = self.isChecked()
        hover = self.underMouse()
        if on:
            p.setPen(Qt.NoPen)
            p.setBrush(t.c("accent-soft"))
            p.drawRoundedRect(r, 10, 10)
        p.setPen(QPen(t.c("accent") if on else (t.c("border-strong") if hover else t.c("border")), 1))
        p.setBrush(t.c("surface-3") if (on or hover) else t.c("surface-2"))
        p.drawRoundedRect(r.adjusted(2 if on else 0, 2 if on else 0, -2 if on else 0, -2 if on else 0), 9, 9)
        pv = QRectF(5, 5, self.width() - 10, (self.width() - 10) / 2.6)
        animate = on or hover
        tt = (time.monotonic() - self.page.t0) if animate else 1.7
        st = self.page.current()
        if on:
            rgb = None if st.rainbow else st.color
            speed, opt, bright = st.speed, st.option, max(1, st.brightness)
        else:
            rgb, speed, opt, bright = DEMO.get(self.m.key), 2, None, 4
            if rgb == 0:
                rgb = None
        if self.side:
            paint_strip(p, pv, self.m.key, tt, rgb, speed, opt, bright)
        else:
            paint_preview(p, pv, self.m.key, tt, rgb, speed, opt, bright)
        p.setFont(font(12.5, 500))
        p.setPen(t.c("accent") if on else t.c("text-1"))
        p.drawText(QRectF(9, pv.bottom() + 4, self.width() - 30, self.height() - pv.bottom() - 8),
                   Qt.AlignLeft | Qt.AlignVCenter, MODE_NAMES.get(self.m.key, self.m.label))
        if self.live:
            p.setPen(Qt.NoPen)
            p.setBrush(t.c("success"))
            p.drawEllipse(QRectF(self.width() - 14, pv.bottom() + 4 + (self.height() - pv.bottom() - 8) / 2 - 3, 6, 6))


class BigPreview(QWidget):
    def __init__(self, page: "LightPage"):
        super().__init__()
        self.page = page
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(120)

    def resizeEvent(self, e):
        self.setFixedHeight(round(self.width() / 2.35))

    def paintEvent(self, _e):
        p = QPainter(self)
        st = self.page.current()
        rgb = None if st.rainbow else st.color
        fn = paint_strip if self.page.side else paint_preview
        fn(p, QRectF(0, 0, self.width(), self.height()), st.mode, time.monotonic() - self.page.t0, rgb, st.speed,
           st.option, max(1, st.brightness), radius=10)


class ZoneButton(QToolButton):
    """Botón de zona (Luz de teclas / Tira lateral) con título y resumen."""

    def __init__(self, title: str, icon: str):
        super().__init__()
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        ic = W.icon_label(icon, "accent", 18)
        self.ic_name = icon
        self.ic = ic
        self.t = W.label(title, "strong")
        self.s = W.label("", "cap")
        for w in (ic, self.t, self.s):
            w.setAttribute(Qt.WA_TransparentForMouseEvents)
        W.hbox(ic, W.vbox(self.t, self.s, spacing=0), "stretch", spacing=12, margins=(12, 0, 12, 0), parent=self)
        self.toggled.connect(lambda on: W.set_icon(self.ic, self.ic_name, "accent" if on else "text-2", 18))


class LightPage(Page):
    def __init__(self, win):
        super().__init__(win)
        self.t0 = time.monotonic()
        self.hovered: ModeCard | None = None
        self.side = False
        self.state = {False: L.LightSetting(mode="static"), True: L.LightSetting(mode="static")}
        self.device = {False: None, True: None}
        self.cards: dict[bool, list[ModeCard]] = {False: [], True: []}

        header = W.PageHeader("Iluminación", "Efectos para las teclas y para la tira lateral. "
                                             "Pasa el ratón por un efecto para verlo en movimiento.")
        self.live = W.Switch()
        self.live.setToolTip("Cada cambio se envía al teclado al momento")
        header.actions.addWidget(self.live)
        header.actions.addWidget(W.label("Aplicar en vivo", "strong"))
        header.actions.addSpacing(4)
        self.b_read = header.add(W.button("Leer", "secondary", "leer", on_click=self.read))
        self.b_apply = header.add(W.button("Aplicar", "primary", "aplicar", on_click=self.apply))
        self.live.toggled.connect(self._live_toggled)
        self.lay.addWidget(header)

        # zonas
        zone = W.Segmented(kind="zone", block=True)
        self.z_keys = ZoneButton("Luz de teclas", "teclas")
        self.z_side = ZoneButton("Tira lateral", "tira")
        for i, b in enumerate((self.z_keys, self.z_side)):
            zone.group.addButton(b, i)
            zone.buttons.append(b)
            zone.data.append(bool(i))
            zone.lay.addWidget(b)
        self.z_keys.setChecked(True)
        zone.changed.connect(self._zone)
        self.lay.addWidget(zone)

        # modos
        self.modes_card, ml = W.card(padding=(16, 14, 16, 16), spacing=12)
        self.modes_title = W.label("Modo", "sub")
        self.modes_count = W.label("", "cap")
        live_dot = W.label("●", tone="success")
        live_dot.setStyleSheet("font-size: 9px;")
        ml.addLayout(W.hbox(self.modes_title, self.modes_count, "stretch", live_dot,
                            W.label("En el teclado", "cap"), spacing=8))
        self.grids = {}
        for side, modes in ((False, L.MODES), (True, L.SIDE_MODES)):
            box = QWidget()
            g = QGridLayout(box)
            g.setContentsMargins(0, 0, 0, 0)
            g.setSpacing(12)
            for m in modes:
                c = ModeCard(m, side, self)
                c.clicked.connect(lambda _=False, m=m: self.pick_mode(m.key))
                self.cards[side].append(c)
            self.grids[side] = (box, g)
            ml.addWidget(box)
        ml.addStretch(1)
        self.modes_card.installEventFilter(self)

        # panel derecho
        self.panel, pl = W.card(padding=(16, 16, 16, 16), spacing=12)
        self.panel.setFixedWidth(320)
        self.big = BigPreview(self)
        self.p_name = W.label("", "title")
        self.p_state = W.pill("En el teclado", "ok")
        pl.addWidget(self.big)
        pl.addLayout(W.hbox(self.p_name, "stretch", self.p_state))
        self.bright = W.TickSlider(0, 4)
        self.bright_v = W.label("4 / 4", "mono2")
        pl.addLayout(W.hbox(W.icon_label("brillo"), W.label("Brillo", "strong"), "stretch", self.bright_v, spacing=8))
        pl.addWidget(self.bright)
        self.speed = W.TickSlider(0, 4)
        self.speed_v = W.label("", "mono2")
        self.speed_lbl = W.label("Velocidad", "strong")
        pl.addLayout(W.hbox(W.icon_label("velocidad"), self.speed_lbl, "stretch", self.speed_v, spacing=8))
        pl.addWidget(self.speed)
        self.color_hex = W.label("", "mono2")
        self.color_lbl = W.label("Color", "strong")
        pl.addLayout(W.hbox(W.icon_label("color"), self.color_lbl, "stretch", self.color_hex, spacing=8))
        self.eyed = QToolButton()
        self.eyed.setCursor(Qt.PointingHandCursor)
        self.eyed.setToolTip("Otro color…")
        self.eyed.setFixedSize(26, 26)
        self.eyed.setStyleSheet("")
        W.set_icon(self.eyed, "cuentagotas", "text-1", 14)
        self.swatches = W.SwatchRow(W.KEY_SWATCHES, 24, extra=self.eyed)
        self.swatches.picked.connect(self.set_color)
        self.eyed.clicked.connect(self._custom_color)
        pl.addWidget(self.swatches)
        self.rainbow = W.Switch(rgb=True)
        self.rainbow_lbl = W.label("Arcoíris <span style='font-weight:400'>(colores cíclicos)</span>", "strong",
                                   rich=True)
        pl.addLayout(W.hbox(W.icon_label("arcoiris"), self.rainbow_lbl, "stretch", self.rainbow, spacing=8))
        self.var_lbl = W.label("Variante", "strong")
        pl.addLayout(W.hbox(W.icon_label("mas-opciones"), self.var_lbl, "stretch", spacing=8))
        self.var_host = QWidget()
        self.var_lay = W.vbox(spacing=0, parent=self.var_host)
        pl.addWidget(self.var_host)
        self.var_hint = W.label("", "cap", wrap=True)
        pl.addWidget(self.var_hint)
        pl.addStretch(1)
        self.variant: W.Segmented | None = None

        row = W.hbox(spacing=16)
        row.addWidget(self.modes_card, 1)
        row.addWidget(self.panel, 0, Qt.AlignTop)
        self.lay.addLayout(row)
        self.lay.addStretch(1)

        self.bright.valueChanged.connect(lambda v: self._edit(brightness=v))
        self.speed.valueChanged.connect(lambda v: self._edit(speed=v))
        self.rainbow.toggled.connect(lambda on: self._edit(rainbow=on))

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(33)
        self.live_timer = QTimer(self)
        self.live_timer.setSingleShot(True)
        self.live_timer.setInterval(250)
        self.live_timer.timeout.connect(self.apply)
        self._layout_grid()
        self._zone(False)

    # ------------------------------------------------------------ estado
    def current(self) -> L.LightSetting:
        return self.state[self.side]

    def mdef(self) -> L.ModeDef:
        table = L.SIDE_MODE_BY_KEY if self.side else L.MODE_BY_KEY
        return table.get(self.current().mode) or (L.SIDE_MODES if self.side else L.MODES)[0]

    def _tick(self):
        if not self.isVisible():
            return
        for c in self.cards[self.side]:
            if c.isChecked() or c is self.hovered:
                c.update()
        self.big.update()

    def eventFilter(self, obj, ev):
        if obj is self.modes_card and ev.type() == ev.Type.Resize:
            self._layout_grid()
        return False

    def _layout_grid(self):
        w = max(300, self.modes_card.width() - 32)
        cols = max(2, min(5, w // 150))
        for side in (False, True):
            box, g = self.grids[side]
            if getattr(box, "_cols", None) == cols:
                continue
            box._cols = cols
            for c in self.cards[side]:
                g.removeWidget(c)
            for i, c in enumerate(self.cards[side]):
                g.addWidget(c, i // cols, i % cols)
            for i in range(5):
                g.setColumnStretch(i, 1 if i < cols else 0)

    def _zone(self, side):
        self.side = bool(side)
        self.grids[False][0].setVisible(not self.side)
        self.grids[True][0].setVisible(self.side)
        n = len(L.SIDE_MODES if self.side else L.MODES)
        self.modes_count.setText(f"{n} efectos")
        self.show_state()

    def _summaries(self):
        self.z_keys.s.setText(_desc(self.state[False], False))
        self.z_side.s.setText(_desc(self.state[True], True))

    def show_state(self):
        s = self.current()
        m = self.mdef()
        for c in self.cards[self.side]:
            c.setChecked(c.m.key == s.mode)
            dev = self.device[self.side]
            c.live = dev is not None and dev.mode == c.m.key
            c.update()
        self.p_name.setText(MODE_NAMES.get(m.key, m.label))
        for w in (self.bright, self.speed, self.rainbow):
            w.blockSignals(True)
        self.bright.setValue(s.brightness)
        self.speed.setValue(s.speed)
        self.rainbow.setChecked(s.rainbow)
        for w in (self.bright, self.speed, self.rainbow):
            w.blockSignals(False)
        self.bright_v.setText(f"{s.brightness} / 4")
        self.speed_v.setText(f"{s.speed} / 4")
        name = MODE_NAMES.get(m.key, m.label)
        off = m.kind in ("off", "screen")
        W.disable_with_reason(self.bright, f"{name} no usa brillo" if off else None)
        W.disable_with_reason(self.speed, None if m.speed else f"{name} no usa velocidad")
        color_ok = m.color or m.kind == "music"
        W.disable_with_reason(self.rainbow, None if color_ok else f"{name} no usa color")
        for sw in self.swatches.swatches:
            W.disable_with_reason(sw, None if (color_ok and not s.rainbow) else
                                  (f"{name} no usa color" if not color_ok else "Desactiva el arcoíris para elegir color"))
        self.eyed.setEnabled(color_ok and not s.rainbow)
        self.swatches.select(s.color if color_ok and not s.rainbow else None)
        self.color_hex.setText(f"#{s.color:06X}" if color_ok and not s.rainbow else "—")
        self._build_variant(m, s)
        self._summaries()
        self._update_apply()

    def _build_variant(self, m: L.ModeDef, s: L.LightSetting):
        if self.variant is not None:
            self.variant.setParent(None)
            self.variant.deleteLater()
            self.variant = None
        while self.var_lay.count():
            it = self.var_lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        name = MODE_NAMES.get(m.key, m.label)
        if m.kind == "picture":
            opts = [(str(i), f"{i}") for i in range(1, 6)]
            hint = "Qué imagen de usuario mostrar (Colores por tecla pinta la 1)."
        else:
            opts = [(o, OPTION_NAMES.get(o, lab.capitalize())) for o, lab in zip(m.options, m.option_labels)]
            hint = ""
        if not opts:
            empty = W.Segmented(block=True)
            b = empty.add("—", None)
            b.setEnabled(False)
            empty.setEnabled(False)
            self.var_lay.addWidget(empty)
            self.variant = empty
            self.var_hint.setText(f"{name} no tiene variantes")
            return
        seg = W.Segmented(block=True)
        for key, lab in opts:
            ic = OPTION_ICONS.get(key)
            b = seg.add("" if (ic and len(opts) > 3) else lab, key, icon=ic, tip=lab)
            b.setToolButtonStyle(Qt.ToolButtonIconOnly if (ic and len(opts) > 3) else
                                 (Qt.ToolButtonTextBesideIcon if ic else Qt.ToolButtonTextOnly))
        cur = s.option if s.option in [o for o, _ in opts] else opts[0][0]
        seg.setValue(cur)
        if s.option != cur:
            s.option = cur
        seg.changed.connect(lambda v: self._edit(option=v))
        self.var_lay.addWidget(seg)
        self.variant = seg
        self.var_hint.setText(hint or OPTION_NAMES.get(cur, ""))

    def _update_apply(self):
        dev = self.device[self.side]
        same = dev is not None and dev == self.current()
        self.p_state.setText("En el teclado" if same else "Sin aplicar")
        W.set_prop(self.p_state, "pill", "ok" if same else "warn")
        if self.live.isChecked():
            W.disable_with_reason(self.b_apply, "Con «Aplicar en vivo» cada cambio se envía al momento")
        else:
            W.disable_with_reason(self.b_apply, None if not same else "No hay cambios que aplicar")

    # ------------------------------------------------------------ edición
    def pick_mode(self, key: str):
        s = self.current()
        table = L.SIDE_MODE_BY_KEY if self.side else L.MODE_BY_KEY
        m = table[key]
        opt = s.option if s.option in m.options else (m.options[0] if m.options else ("1" if m.kind == "picture"
                                                                                       else None))
        self.state[self.side] = replace(s, mode=key, option=opt)
        self.show_state()
        self._changed()

    def _edit(self, **kw):
        self.state[self.side] = replace(self.current(), **kw)
        self.show_state()
        self._changed()

    def set_color(self, rgb: int):
        self._edit(color=rgb, rainbow=False)

    def _custom_color(self):
        pop = W.ColorPopover(self.current().color, W.KEY_SWATCHES, self.window())
        pop.colorChanged.connect(self.set_color)
        pop.popup_at(self.eyed)

    def _changed(self):
        if self.live.isChecked():
            self.live_timer.start()

    def _live_toggled(self, on):
        self._update_apply()
        if on:
            self._changed()

    # ------------------------------------------------------------ teclado
    def on_connected(self):
        self.read()

    def on_profile(self):
        self.read()

    def read(self):
        kb = self.kb
        if not kb:
            return

        def work():
            return kb.get_light(), kb.get_side_light()

        def done(r):
            self.device = {False: r[0], True: r[1]}
            self.state = {False: replace(r[0]), True: replace(r[1])}
            self.show_state()
            self.win.pages["colors"].light_changed(r[0])

        self.win.run(work, on_done=done, label="Leyendo luz…", retry=self.read)

    def apply(self):
        kb = self.kb
        if not kb:
            return
        side = self.side
        s = replace(self.current())

        def done(_):
            self.device[side] = s
            if side == self.side:
                self.show_state()
            if not side:
                self.win.pages["colors"].light_changed(s)
            if not self.live.isChecked():
                self.win.toast("ok", ("Tira lateral: " if side else "Luz: ") + _desc(s, side))

        self.win.run(kb.set_side_light if side else kb.set_light, s, on_done=done, label="Aplicando luz…",
                     quiet=self.live.isChecked(), retry=self.apply)

    def set_user_mode(self):
        """Activa «Imagen de usuario» en la luz de teclas (desde Colores por tecla)."""
        s = self.device[False] or self.state[False]
        self.state[False] = replace(s, mode="user", option="1")
        prev_side = self.side
        self.side = False
        self.apply()
        self.side = prev_side
        self.show_state()

