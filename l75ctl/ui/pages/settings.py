"""Sección Ajustes: rendimiento, reposo, opciones, información y zona peligrosa."""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QComboBox, QFrame

from ... import __version__
from ... import protocol as P
from ...keyboard import KeyboardOptions, SleepTimes
from .. import widgets as W
from ...i18n import LANGUAGES, language
from ...i18n import t as tr
from ..window import Page

OPTIONS = [("win_lock", "candado", "Lock Windows key", "Avoids opening the Start menu in the middle of a game."),
           ("mac_mode", "comando", "Mac mode", "Modifier layout for macOS (⌥ and ⌘)."),
           ("wasd_arrows_swap", "intercambiar", "Swap WASD and arrows",
            "WASD work as arrows and the arrows as WASD.")]
INFO = [("fw", "Firmware"), ("id", "Model ID"), ("conn", "Connection"), ("profile", "Active profile"),
        ("battery", "Battery"), ("version", "App version")]


def _card_title(icon: str, text: str, extra: str = ""):
    t = W.label(text, "sub")
    lay = W.hbox(W.icon_label(icon, "text-2", 18), t, spacing=10)
    if extra:
        lay.addWidget(W.label(extra, "cap"))
    lay.addStretch(1)
    return lay


class SettingsPage(Page):
    def __init__(self, win):
        super().__init__(win)
        self.loaded: dict | None = None
        self.opts = KeyboardOptions()

        self.header = W.PageHeader(tr("Settings"), "")
        self.header.add(W.button(tr("Read"), "secondary", "leer", on_click=self.load))
        self.b_apply = self.header.add(W.button(tr("Apply changes"), "primary", "aplicar", on_click=self.apply))
        self.lay.addWidget(self.header)

        # --- rendimiento
        perf, pl = W.card(spacing=10)
        pl.addLayout(_card_title("sondeo", tr("Performance")))
        pl.addSpacing(2)
        pl.addWidget(W.label(tr("Polling rate"), "strong"))
        self.rate = W.Segmented([(f"{hz} Hz", hz) for hz in (125, 250, 500, 1000)], block=True, mono=True)
        self.rate.setValue(1000)
        self.rate.changed.connect(self._dirty)
        pl.addWidget(self.rate)
        pl.addWidget(W.label(tr("Higher means less latency. 1000 Hz is usual for gaming."), "cap"))
        pl.addSpacing(4)
        pl.addWidget(W.label(tr("Debounce"), "strong"))
        self.deb_sl = W.TickSlider(0, 50, ticks=False)
        self.deb = W.Stepper(0, 50, 1, "ms", buttons=False, width=36)
        self.deb_sl.valueChanged.connect(lambda v: self.deb.setValue(v))
        self.deb.valueChanged.connect(self._deb)
        pl.addLayout(W.hbox(self.deb_sl, self.deb, spacing=16))
        pl.addWidget(W.label(tr("Raise it only if a key types twice."), "cap"))
        pl.addStretch(1)

        # --- reposo
        sleep, sl = W.card(spacing=10)
        sl.addLayout(_card_title("luna", tr("Sleep"), tr("(wireless mode)")))
        sl.addSpacing(2)
        self.sleep = W.Stepper(0, 60, 2, "min")
        self.deep = W.Stepper(10, 60, 28, "min")
        for st, t, h in ((self.sleep, tr("Sleep after"), tr("0 = never")),
                         (self.deep, tr("Deep sleep after"), tr("Between 10 and 60 min"))):
            st.valueChanged.connect(self._dirty)
            sl.addLayout(W.hbox(W.vbox(W.label(t, "strong"), W.label(h, "cap"), spacing=0), "stretch", st))
        sl.addWidget(W.label(tr("Only applies over Bluetooth or 2.4 GHz."), "cap"))
        sl.addStretch(1)

        # --- opciones
        opt, ol = W.card(spacing=0)
        ol.addLayout(_card_title("ajustes", tr("Options")))
        ol.addSpacing(10)
        self.switches: dict[str, W.Switch] = {}
        for i, (key, icon, title, desc) in enumerate(OPTIONS):
            row = QFrame()
            row.setProperty("kv", "true")
            box = QFrame()
            box.setProperty("iconbox", "true")
            box.setFixedSize(32, 32)
            W.hbox(W.icon_label(icon, "text-2", 16), margins=(7, 7, 7, 7), parent=box)
            sw = W.Switch()
            sw.toggled.connect(self._dirty)
            self.switches[key] = sw
            W.hbox(box, 4, W.vbox(W.label(tr(title), "strong"), W.label(tr(desc), "cap"), spacing=0), "stretch", sw,
                   spacing=10, margins=(0, 10, 0, 10), parent=row)
            ol.addWidget(row)
        # idioma de la app (no es un ajuste del teclado: se aplica al momento)
        lang_row = QFrame()
        lang_row.setProperty("kv", "last")
        lbox = QFrame()
        lbox.setProperty("iconbox", "true")
        lbox.setFixedSize(32, 32)
        W.hbox(W.icon_label("info", "text-2", 16), margins=(7, 7, 7, 7), parent=lbox)
        self.lang = QComboBox()
        self.lang.addItem(tr("Automatic (system)"), "auto")
        for code, name in LANGUAGES.items():
            self.lang.addItem(name, code)
        saved = QSettings("l75-config", "l75-config").value("language", "auto")
        self.lang.setCurrentIndex(max(0, self.lang.findData(saved)))
        self.lang.activated.connect(self._language)
        W.hbox(lbox, 4, W.vbox(W.label(tr("Language") + ("" if language() == "en" else " · Language"), "strong"),
                               W.label(tr("Language of the app (not of the keyboard)."), "cap"), spacing=0),
               "stretch", self.lang, spacing=10, margins=(0, 10, 0, 10), parent=lang_row)
        ol.addWidget(lang_row)
        ol.addStretch(1)

        # --- información
        info, il = W.card(spacing=0)
        il.addLayout(_card_title("chip", tr("Information")))
        il.addSpacing(8)
        self.kv: dict[str, object] = {}
        for i, (key, name) in enumerate(INFO):
            row = QFrame()
            row.setProperty("kv", "last" if i == len(INFO) - 1 else "true")
            row.setFixedHeight(34)
            v = W.label("—", "kv-v")
            v.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self.kv[key] = v
            W.hbox(W.label(tr(name), "kv-l"), "stretch", v, parent=row)
            il.addWidget(row)
        self.kv["version"].setText(f"L75 Config {__version__}")

        grid = W.vbox(spacing=16)
        for a, b in ((perf, sleep), (opt, info)):
            row = W.hbox(spacing=16)
            row.addWidget(a, 1)
            row.addWidget(b, 1)
            grid.addLayout(row)
        self.lay.addLayout(grid)

        # --- zona peligrosa
        danger = QFrame()
        danger.setProperty("card", "danger")
        ic = QFrame()
        ic.setProperty("iconbox", "err")
        ic.setFixedSize(36, 36)
        W.hbox(W.icon_label("aviso", "error", 18), margins=(9, 9, 9, 9), parent=ic)
        self.b_factory = W.button(tr("Factory reset…"), "danger", "restaurar", on_click=self.factory)
        dl = W.hbox(ic, spacing=14, margins=(18, 14, 18, 14), parent=danger)
        dl.addLayout(W.vbox(W.label(tr("Danger zone"), "sub", tone="error"),
                            W.label(tr("<b>Factory reset</b> returns the keyboard to its original state: keys, "
                                       "macros, lighting and settings of all 3 profiles."), "body2", wrap=True,
                                    rich=True),
                            spacing=2), 1)
        dl.addWidget(self.b_factory)
        self.lay.addWidget(danger)
        self.lay.addStretch(1)
        self._header()
        W.disable_with_reason(self.b_apply, tr("No changes to apply"))

    def _header(self):
        self.header.subtitle.setText(tr("Performance, sleep and keyboard options for profile {n}.").format(
            n=self.win.profile + 1))

    def _deb(self, v):
        self.deb_sl.blockSignals(True)
        self.deb_sl.setValue(v)
        self.deb_sl.blockSignals(False)
        self._dirty()

    # ------------------------------------------------------------ estado
    def _values(self) -> dict:
        return {"rate": self.rate.value(), "deb": self.deb.value(), "sleep": self.sleep.value(),
                "deep": self.deep.value(), **{k: sw.isChecked() for k, sw in self.switches.items()}}

    def _dirty(self, *_a):
        same = self.loaded is not None and self._values() == self.loaded
        reason = tr("Connect the keyboard") if not self.kb else (tr("No changes to apply") if same else None)
        W.disable_with_reason(self.b_apply, reason)

    def on_connected(self):
        self._header()
        self.load()

    def on_profile(self):
        self._header()
        self.load()

    def load(self):
        kb = self.kb
        if not kb:
            return

        def work():
            return (kb.get_report_rate(), kb.get_debounce(), kb.get_sleep(), kb.get_options(),
                    kb.firmware_version(), kb.battery(), kb.device_id())

        self.win.run(work, on_done=self._loaded, label=tr("Reading settings…"), retry=self.load)

    def _loaded(self, r):
        rate, deb, sl, opts, fw, bat, dev_id = r
        for w in (self.deb, self.sleep, self.deep):
            w.blockSignals(True)
        if rate:
            self.rate.setValue(rate)
        self.deb.setValue(deb)
        self.deb_sl.blockSignals(True)
        self.deb_sl.setValue(deb)
        self.deb_sl.blockSignals(False)
        self.sleep.setValue(min(60, sl.bt // 60))
        self.deep.setValue(max(10, min(60, sl.deep_bt // 60)))
        for w in (self.deb, self.sleep, self.deep):
            w.blockSignals(False)
        self.opts = opts
        for k, sw in self.switches.items():
            sw.blockSignals(True)
            sw.setChecked(getattr(opts, k))
            sw.blockSignals(False)
        self.loaded = self._values()
        kb = self.kb
        self.kv["fw"].setText(f"{fw >> 8}.{fw & 0xFF:02d}")
        self.kv["id"].setText(f"{dev_id}" + (" (L75)" if dev_id in P.DEVICE_IDS_L75 else ""))
        if kb.is_demo:
            conn = tr("Simulated (demo mode)")
        elif kb.bus == "bt":
            conn = f"Bluetooth · {P.VID:04x}:4012"
        else:
            conn = tr("USB-C cable") + f" · {P.VID:04x}:{P.PID_WIRED:04x}"
        self.kv["conn"].setText(conn)
        self.kv["profile"].setText(tr("{n} of 3").format(n=self.win.profile + 1))
        self.kv["battery"].setText(f"{bat[0]} % · {tr(bat[1])}")
        self.win.topbar.set_battery(*bat)
        self._dirty()

    def apply(self):
        kb = self.kb
        if not kb:
            return
        v = self._values()
        o = replace(self.opts, win_lock=v["win_lock"], mac_mode=v["mac_mode"], wasd_arrows_swap=v["wasd_arrows_swap"])
        sl = SleepTimes(v["sleep"] * 60, v["sleep"] * 60, v["deep"] * 60, v["deep"] * 60)

        def work():
            kb.set_report_rate(v["rate"])
            kb.set_debounce(v["deb"])
            kb.set_sleep(sl)
            kb.set_options(o)

        def done(_):
            self.opts = o
            self.loaded = v
            self._dirty()
            self.win.toast("ok", tr("Settings saved to the keyboard"))

        self.win.run(work, on_done=done, label=tr("Saving settings…"), retry=self.apply)

    def factory(self):
        if not self.kb:
            return
        self.win.confirm(tr("Factory reset?"),
                         tr("Remaps, macros, lighting and settings of all 3 profiles will be erased.") +
                         " <b>" + tr("This cannot be undone.") + "</b>",
                         tr("Factory reset"),
                         lambda: self.win.run(self.kb.factory_reset, on_done=lambda _: self._after_reset(),
                                              label=tr("Resetting to factory…")),
                         danger=True, icon="aviso", require=tr("RESTORE"))

    def _language(self, _i):
        code = self.lang.currentData()
        QSettings("l75-config", "l75-config").setValue("language", code)
        self.win.set_language(code)

    def _after_reset(self):
        self.win.toast("ok", tr("Keyboard reset to factory"))
        self.win.on_connected()
