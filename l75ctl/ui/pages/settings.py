"""Sección Ajustes: rendimiento, reposo, opciones, información y zona peligrosa."""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame

from ... import __version__
from ... import protocol as P
from ...keyboard import KeyboardOptions, SleepTimes
from .. import widgets as W
from ..window import Page

OPTIONS = [("win_lock", "candado", "Bloquear tecla Windows", "Evita abrir el menú Inicio en mitad de una partida."),
           ("mac_mode", "comando", "Modo Mac", "Distribución de modificadores para macOS (⌥ y ⌘)."),
           ("wasd_arrows_swap", "intercambiar", "Intercambiar WASD y flechas",
            "WASD funcionan como flechas y las flechas como WASD.")]


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

        self.header = W.PageHeader("Ajustes", "")
        self.header.add(W.button("Leer", "secondary", "leer", on_click=self.load))
        self.b_apply = self.header.add(W.button("Aplicar cambios", "primary", "aplicar", on_click=self.apply))
        self.lay.addWidget(self.header)

        # --- rendimiento
        perf, pl = W.card(spacing=10)
        pl.addLayout(_card_title("sondeo", "Rendimiento"))
        pl.addSpacing(2)
        pl.addWidget(W.label("Tasa de sondeo", "strong"))
        self.rate = W.Segmented([(f"{hz} Hz", hz) for hz in (125, 250, 500, 1000)], block=True, mono=True)
        self.rate.setValue(1000)
        self.rate.changed.connect(self._dirty)
        pl.addWidget(self.rate)
        pl.addWidget(W.label("Más alto, menos latencia. 1000 Hz es lo habitual para jugar.", "cap"))
        pl.addSpacing(4)
        pl.addWidget(W.label("Debounce", "strong"))
        self.deb_sl = W.TickSlider(0, 50, ticks=False)
        self.deb = W.Stepper(0, 50, 1, "ms", buttons=False, width=36)
        self.deb_sl.valueChanged.connect(lambda v: self.deb.setValue(v))
        self.deb.valueChanged.connect(self._deb)
        pl.addLayout(W.hbox(self.deb_sl, self.deb, spacing=16))
        pl.addWidget(W.label("Súbelo solo si alguna tecla escribe dos veces.", "cap"))
        pl.addStretch(1)

        # --- reposo
        sleep, sl = W.card(spacing=10)
        sl.addLayout(_card_title("luna", "Reposo", "(modo inalámbrico)"))
        sl.addSpacing(2)
        self.sleep = W.Stepper(0, 60, 2, "min")
        self.deep = W.Stepper(10, 60, 28, "min")
        for st, t, h in ((self.sleep, "Reposo tras", "0 = nunca"),
                         (self.deep, "Reposo profundo tras", "Entre 10 y 60 min")):
            st.valueChanged.connect(self._dirty)
            sl.addLayout(W.hbox(W.vbox(W.label(t, "strong"), W.label(h, "cap"), spacing=0), "stretch", st))
        sl.addWidget(W.label("Solo cuenta por Bluetooth o 2.4 GHz.", "cap"))
        sl.addStretch(1)

        # --- opciones
        opt, ol = W.card(spacing=0)
        ol.addLayout(_card_title("ajustes", "Opciones"))
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
            W.hbox(box, 4, W.vbox(W.label(title, "strong"), W.label(desc, "cap"), spacing=0), "stretch", sw,
                   spacing=10, margins=(0, 10, 0, 10), parent=row)
            ol.addWidget(row)
        ol.addStretch(1)

        # --- información
        info, il = W.card(spacing=0)
        il.addLayout(_card_title("chip", "Información"))
        il.addSpacing(8)
        self.kv: dict[str, object] = {}
        names = ["Firmware", "ID de modelo", "Conexión", "Perfil activo", "Batería", "Versión de la app"]
        for i, n in enumerate(names):
            row = QFrame()
            row.setProperty("kv", "last" if i == len(names) - 1 else "true")
            row.setFixedHeight(34)
            v = W.label("—", "kv-v")
            v.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self.kv[n] = v
            W.hbox(W.label(n, "kv-l"), "stretch", v, parent=row)
            il.addWidget(row)
        self.kv["Versión de la app"].setText(f"L75 Config {__version__}")

        grid = W.vbox(W.hbox(perf, sleep, spacing=16), W.hbox(opt, info, spacing=16), spacing=16)
        self.lay.addLayout(grid)

        # --- zona peligrosa
        danger = QFrame()
        danger.setProperty("card", "danger")
        ic = QFrame()
        ic.setProperty("iconbox", "err")
        ic.setFixedSize(36, 36)
        W.hbox(W.icon_label("aviso", "error", 18), margins=(9, 9, 9, 9), parent=ic)
        self.b_factory = W.button("Restaurar de fábrica…", "danger", "restaurar", on_click=self.factory)
        dl = W.hbox(ic, spacing=14, margins=(18, 14, 18, 14), parent=danger)
        dl.addLayout(W.vbox(W.label("Zona peligrosa", "sub", tone="error"),
                            W.label("<b>Restaurar de fábrica</b> devuelve el teclado a su estado original: teclas, "
                                    "macros, luces y ajustes de los 3 perfiles.", "body2", wrap=True, rich=True),
                            spacing=2), 1)
        dl.addWidget(self.b_factory)
        self.lay.addWidget(danger)
        self.lay.addStretch(1)
        self._header()
        W.disable_with_reason(self.b_apply, "No hay cambios que aplicar")

    def _header(self):
        self.header.subtitle.setText(f"Rendimiento, reposo y opciones del teclado para el perfil {self.win.profile + 1}.")

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
        reason = "Conecta el teclado" if not self.kb else ("No hay cambios que aplicar" if same else None)
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

        self.win.run(work, on_done=self._loaded, label="Leyendo ajustes…", retry=self.load)

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
        self.kv["Firmware"].setText(f"{fw >> 8}.{fw & 0xFF:02d}")
        self.kv["ID de modelo"].setText(f"{dev_id}" + (" (L75)" if dev_id in P.DEVICE_IDS_L75 else ""))
        if kb.is_demo:
            conn = "Simulado (modo demo)"
        elif kb.bus == "bt":
            conn = f"Bluetooth · {P.VID:04x}:4012"
        else:
            conn = f"Cable USB-C · {P.VID:04x}:{P.PID_WIRED:04x}"
        self.kv["Conexión"].setText(conn)
        self.kv["Perfil activo"].setText(f"{self.win.profile + 1} de 3")
        self.kv["Batería"].setText(f"{bat[0]} % · {bat[1]}")
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
            self.win.toast("ok", "Ajustes guardados en el teclado")

        self.win.run(work, on_done=done, label="Guardando ajustes…", retry=self.apply)

    def factory(self):
        if not self.kb:
            return
        self.win.confirm("¿Restaurar de fábrica?",
                         "Se borrarán reasignaciones, macros, luces y ajustes de los 3 perfiles. "
                         "<b>No se puede deshacer.</b>",
                         "Restaurar de fábrica",
                         lambda: self.win.run(self.kb.factory_reset, on_done=lambda _: self._after_reset(),
                                              label="Restaurando de fábrica…"),
                         danger=True, icon="aviso", require="RESTAURAR")

    def _after_reset(self):
        self.win.toast("ok", "Teclado restaurado de fábrica")
        self.win.on_connected()
