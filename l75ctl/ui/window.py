"""Ventana principal: barra lateral, barra superior, páginas, toasts y diálogos."""

from __future__ import annotations

import os
import traceback

from PySide6.QtCore import QObject, QRectF, QRunnable, QSettings, Qt, QThreadPool, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QPainter, QPen
from PySide6.QtWidgets import (QApplication, QButtonGroup, QFrame, QLabel, QMainWindow, QProgressBar, QScrollArea,
                               QSizePolicy, QStackedWidget, QToolButton, QVBoxLayout, QWidget)

from .. import __version__
from ..keyboard import L75
from ..i18n import t as tr
from ..transport import Cancelled, NoResponse, PermissionDenied, list_devices
from . import widgets as W
from .theme import font, paint_rgb_line, theme

SECTIONS = [  # (key, English name -> tr(), icon)
    ("keys", "Keys", "teclas"),
    ("light", "Lighting", "iluminacion"),
    ("colors", "Per-key colours", "colores"),
    ("macros", "Macros", "macros"),
    ("screen", "Screen", "pantalla"),
    ("settings", "Settings", "ajustes"),
]

REPO_URL = "https://github.com/GiomarOsorio/l75-config"


# ---------------------------------------------------------------- tareas en segundo plano


class _Signals(QObject):
    done = Signal(object)
    failed = Signal(object)
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
            self.signals.failed.emit(exc)


# ---------------------------------------------------------------- logo


class Logo(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedSize(32, 32)

    def paintEvent(self, _e):
        t = theme()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(t.c("border-strong"), 1))
        p.setBrush(t.c("surface-3"))
        p.drawRoundedRect(0.5, 0.5, 31, 31, 8, 8)
        p.setPen(t.c("text-1"))
        p.setFont(font(11, 700, mono=True))
        p.drawText(0, 0, 32, 26, Qt.AlignCenter, "75")
        paint_rgb_line(p, QRectF(8, 24, 16, 2), 1.0)


# ---------------------------------------------------------------- barra lateral


class Sidebar(QWidget):
    navigate = Signal(str)

    def __init__(self, win: "MainWindow"):
        super().__init__()
        self.win = win
        self.setObjectName("Sidebar")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedWidth(232)
        self.name = QLabel("L75 Config")
        self.name.setObjectName("AppName")
        self.sub = QLabel("ROYALAXE × ProtoArc")
        self.sub.setObjectName("AppSub")
        self.brand = W.hbox(Logo(), W.vbox(self.name, self.sub, spacing=0), spacing=10)
        self.group = QButtonGroup(self)
        self.buttons: dict[str, QToolButton] = {}
        nav = W.vbox(spacing=2)
        for key, text, icon in SECTIONS:
            b = QToolButton()
            b.setProperty("nav", True)
            b.setText("  " + tr(text))
            b.setCheckable(True)
            b.setFocusPolicy(Qt.NoFocus)
            b.setCursor(Qt.PointingHandCursor)
            b.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            W.set_icon(b, icon, "text-2", 18, active="accent")
            b.clicked.connect(lambda _=False, k=key: self.navigate.emit(k))
            self.group.addButton(b)
            self.buttons[key] = b
            nav.addWidget(b)
        # tema
        self.theme_seg = W.Segmented(kind="true")
        self.b_dark = self.theme_seg.add("", "dark", icon="luna", tip=tr("Dark theme"))
        self.b_light = self.theme_seg.add("", "light", icon="brillo", tip=tr("Light theme"))
        self.theme_seg.setValue(theme().mode)
        self.theme_seg.changed.connect(theme().set_mode)
        self.version = QLabel(f"v{__version__}")
        self.version.setObjectName("Version")
        self.help = W.button("", "ghost", "ayuda", size="sm", tip=tr("About L75 Config"), on_click=win.about)
        self.foot_div = W.divider()
        foot = W.hbox(self.theme_seg, "stretch", self.version, self.help, spacing=6)
        self.lay = W.vbox(self.brand, 18, nav, "stretch", self.foot_div, foot, spacing=0, margins=(12, 18, 12, 12),
                          parent=self)
        self.compact = False

    def set_compact(self, on: bool):
        if on == self.compact:
            return
        self.compact = on
        self.setFixedWidth(72 if on else 232)
        self.name.setVisible(not on)
        self.sub.setVisible(not on)
        self.version.setVisible(not on)
        self.b_light.setVisible(not on)
        self.help.setVisible(not on)
        for key, text, _i in SECTIONS:
            b = self.buttons[key]
            b.setToolButtonStyle(Qt.ToolButtonIconOnly if on else Qt.ToolButtonTextBesideIcon)
            b.setToolTip(tr(text) if on else "")
            b.setText("" if on else "  " + tr(text))


# ---------------------------------------------------------------- barra superior


class Topbar(QWidget):
    def __init__(self, win: "MainWindow"):
        super().__init__()
        self.win = win
        self.setObjectName("Topbar")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedHeight(56)
        # conexión
        self.conn = QFrame()
        self.conn.setObjectName("Conn")
        self.conn.setFixedHeight(32)
        self.conn_icon = QLabel()
        self.conn_icon.setFixedSize(16, 16)
        self.conn_spin = W.Spinner(14, "text-2")
        self.conn_label = QLabel(tr("Looking for the keyboard…"))
        self.conn_label.setObjectName("ConnLabel")
        self.conn_sep = W.divider("vs")
        self.conn_sep.setFixedHeight(14)
        self.conn_sub = QLabel("")
        self.conn_sub.setObjectName("ConnSub")
        W.hbox(self.conn_icon, self.conn_spin, self.conn_label, self.conn_sep, self.conn_sub, spacing=8,
               margins=(10, 0, 12, 0), parent=self.conn)
        # aviso BT
        self.bt_pill = W.pill("  " + tr("Images by cable only"), "warn")
        self.bt_pill.setToolTip(tr("Images cannot be uploaded to the screen over Bluetooth. Plug in the USB-C cable."))
        # acciones sin teclado
        self.b_retry = W.button(tr("Retry"), "secondary", "reintentar", size="sm", on_click=win.reconnect)
        self.b_demo = W.button(tr("Try demo mode"), "ghost", "demo", size="sm",
                               on_click=lambda: win.connect_device(demo=True))
        self.rf_hint = W.label(tr("Connect it by cable or Bluetooth."), "cap")
        # actividad
        self.act_div = W.divider("v")
        self.act_div.setFixedHeight(20)
        self.act_spin = W.Spinner(14, "accent")
        self.act_icon = QLabel()
        self.act_icon.setFixedSize(14, 14)
        self.act_label = QLabel("")
        self.act_label.setObjectName("ActLabel")
        self.act_bar = QProgressBar()
        self.act_bar.setFixedWidth(96)
        self.act_bar.setRange(0, 1000)
        self.act_count = QLabel("")
        self.act_count.setObjectName("ActCount")
        self.act_retry = W.button(tr("Retry"), "link", size="sm")
        self.act_retry.setStyleSheet("")
        self.act_retry.setProperty("variant", "link")
        act = W.hbox(self.act_spin, self.act_icon, self.act_label, self.act_bar, self.act_count, self.act_retry,
                     spacing=8)
        # perfil
        self.profile_lbl = W.label(tr("Profile"), "cap")
        self.profile_group = QButtonGroup(self)
        self.chips = []
        chips = W.hbox(spacing=2)
        for i in range(3):
            c = QToolButton()
            c.setText(str(i + 1))
            c.setProperty("chip", True)
            c.setCheckable(True)
            c.setCursor(Qt.PointingHandCursor)
            self.profile_group.addButton(c, i)
            self.chips.append(c)
            chips.addWidget(c)
        self.profile_group.idClicked.connect(win.change_profile)
        self.batt_div = W.divider("v")
        self.batt_div.setFixedHeight(20)
        self.batt = W.Battery()
        self.batt_text = QLabel("")
        self.batt_text.setObjectName("Batt")
        self.batt_bolt = QLabel()
        self.batt_bolt.setFixedSize(14, 14)
        W.set_icon(self.batt_bolt, "rayo", "success", 14)
        batt = W.hbox(self.batt, self.batt_text, self.batt_bolt, spacing=6)
        self.batt_box = QWidget()
        self.batt_box.setLayout(batt)

        lay = W.hbox(self.conn, self.bt_pill, self.b_retry, self.b_demo, self.rf_hint, self.act_div, spacing=12,
                     margins=(24, 0, 24, 0), parent=self)
        lay.addLayout(act)
        lay.addStretch(1)
        lay.addWidget(self.profile_lbl)
        lay.addLayout(chips)
        lay.addWidget(self.batt_div)
        lay.addWidget(self.batt_box)
        self._err_retry = None
        self.act_retry.clicked.connect(self._retry)
        self.set_activity(None)
        self.set_connection("searching")

    # ---- conexión: searching | usb | bt | demo | none | rf
    def set_connection(self, state: str, sub: str = ""):
        states = {"searching": ("Looking for the keyboard…", None, ""),
                  "usb": ("Connected by cable", "cable", "ok"),
                  "bt": ("Connected by Bluetooth", "inalambrico", "bt"),
                  "demo": ("Demo mode", "demo", "demo"),
                  "none": ("Keyboard not found", "desconectado", "err"),
                  "rf": ("2.4 GHz receiver detected", "receptor", "rf")}
        text, icon, st = states[state]
        self.conn_label.setText(tr(text))
        W.set_prop(self.conn, "state", st)
        color = {"ok": "success", "bt": "accent", "demo": "demo", "err": "error", "rf": "warning"}.get(st, "text-2")
        self.conn_spin.setVisible(icon is None)
        self.conn_icon.setVisible(icon is not None)
        if icon:
            W.set_icon(self.conn_icon, icon, color, 16)
        self.conn_sub.setText(sub)
        self.conn_sub.setVisible(bool(sub))
        self.conn_sep.setVisible(bool(sub))
        connected = state in ("usb", "bt", "demo")
        self.bt_pill.setVisible(state == "bt")
        self.b_retry.setVisible(state in ("none",))
        self.b_demo.setVisible(state in ("none",))
        self.rf_hint.setVisible(state == "rf")
        self.act_div.setVisible(connected)
        for c in self.chips:
            c.setEnabled(connected)
            c.setToolTip("" if connected else tr("Connect the keyboard to change profiles"))
        if not connected:
            self.profile_group.setExclusive(False)
            for c in self.chips:
                c.setChecked(False)
            self.profile_group.setExclusive(True)
        self.batt_div.setVisible(connected)
        self.batt_box.setVisible(connected)
        if not connected:
            self.set_activity(None, idle_text="")

    def set_profile(self, i: int):
        if 0 <= i < 3:
            self.chips[i].setChecked(True)

    def set_battery(self, level: int, status: str):
        self.batt.set(level, status == "charging")
        self.batt_text.setText(f"{level} %")
        self.batt_bolt.setVisible(status == "charging")
        self.batt_box.setToolTip(tr("Battery {n} % · {status}").format(n=level, status=tr(status)))

    # ---- actividad
    def set_activity(self, text: str | None, progress: float | None = None, count: str = "", error: bool = False,
                     retry=None, idle_text: str | None = None):
        if idle_text is None:
            idle_text = tr("In sync")
        self.act_retry.setVisible(error and retry is not None)
        self._err_retry = retry
        if text is None:
            self.act_spin.hide()
            self.act_bar.hide()
            self.act_count.hide()
            self.act_icon.setVisible(bool(idle_text))
            W.set_icon(self.act_icon, "aplicar", "text-2", 14)
            self.act_label.setText(idle_text)
            W.set_prop(self.act_label, "state", "")
            return
        self.act_spin.setVisible(not error)
        self.act_icon.setVisible(error)
        if error:
            W.set_icon(self.act_icon, "error", "error", 14)
        self.act_label.setText(text)
        W.set_prop(self.act_label, "state", "err" if error else "busy")
        self.act_bar.setVisible(progress is not None and not error)
        if progress is not None:
            self.act_bar.setValue(int(progress * 1000))
        self.act_count.setVisible(bool(count) and not error)
        self.act_count.setText(count)

    def _retry(self):
        if self._err_retry:
            f = self._err_retry
            self.set_activity(None)
            f()


# ---------------------------------------------------------------- página base


class Page(QWidget):
    """Página con margen 20 px arriba · 28 px a los lados y desplazamiento vertical."""

    def __init__(self, win: "MainWindow", scroll: bool = True):
        super().__init__()
        self.win = win
        self.body = QWidget()
        self.body.setObjectName("PageBody")
        self.lay = W.vbox(spacing=16, margins=(28, 20, 28, 24), parent=self.body)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        if scroll:
            sa = QScrollArea()
            sa.setObjectName("PageScroll")
            sa.setWidgetResizable(True)
            sa.setFrameShape(QFrame.NoFrame)
            sa.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            sa.setWidget(self.body)
            outer.addWidget(sa)
        else:
            outer.addWidget(self.body)

    @property
    def kb(self) -> L75 | None:
        return self.win.kb

    def on_connected(self):
        pass

    def on_profile(self):
        pass

    def on_shown(self):
        pass


# ---------------------------------------------------------------- ventana


class MainWindow(QMainWindow):
    def __init__(self, demo: bool = False):
        super().__init__()
        from .pages import (ColorsPage, KeysPage, LightPage, MacrosPage, NoKeyboardPage, ScreenPage,
                            SettingsPage)

        self.setWindowTitle("L75 Config")
        self.setMinimumSize(1000, 640)
        self.resize(1280, 800)
        self.kb: L75 | None = None
        self.profile = 0
        self.battery: tuple[int, str] | None = None
        self.info: dict = {}
        self.pool = QThreadPool.globalInstance()
        self._tasks: dict[Task, tuple] = {}

        root = QWidget()
        root.setObjectName("Root")
        self.sidebar = Sidebar(self)
        self.topbar = Topbar(self)
        self.content = QWidget()
        self.content.setObjectName("Content")
        self.stack = QStackedWidget()
        self.stack.setObjectName("Pages")
        self.pages = {
            "keys": KeysPage(self), "light": LightPage(self), "colors": ColorsPage(self),
            "macros": MacrosPage(self), "screen": ScreenPage(self), "settings": SettingsPage(self),
        }
        for p in self.pages.values():
            self.stack.addWidget(p)
        self.empty = NoKeyboardPage(self)
        self.stack.addWidget(self.empty)
        W.vbox(self.topbar, self.stack, spacing=0, parent=self.content)
        lay = W.hbox(self.sidebar, spacing=0, parent=root)
        lay.addWidget(self.content, 1)
        self.setCentralWidget(root)
        self.toaster = W.Toaster(self.content)
        self.current = "keys"
        self.sidebar.navigate.connect(self.go)
        self.sidebar.buttons["keys"].setChecked(True)
        theme().changed.connect(self._theme_changed)
        W.connect_theme_refresh()
        last = QSettings("l75-config", "l75-config").value("section", "keys")
        self.current = last if last in self.pages else "keys"
        self.sidebar.buttons[self.current].setChecked(True)
        self.stack.setCurrentWidget(self.empty)
        QTimer.singleShot(60, lambda: self.connect_device(demo=demo, first=True))

    # ------------------------------------------------------------ navegación
    def go(self, key: str):
        self.current = key
        self.sidebar.buttons[key].setChecked(True)
        QSettings("l75-config", "l75-config").setValue("section", key)
        if self.kb:
            self.stack.setCurrentWidget(self.pages[key])
            self.pages[key].on_shown()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.sidebar.set_compact(self.width() < 1100)

    def _theme_changed(self):
        self.update()
        for w in self.findChildren(QWidget):
            if w.graphicsEffect() is not None and w.objectName() in ("Toast", "Dialog"):
                theme().shadow(w, 2)

    # ------------------------------------------------------------ avisos
    def toast(self, kind: str, text: str, action: str | None = None, on_action=None):
        self.toaster.show_toast(kind, text, action, on_action)

    def confirm(self, title, text, confirm, on_ok, danger=False, icon="restaurar", require=None, extra=None):
        return W.Dialog(self.centralWidget(), title, text, confirm, on_ok, danger=danger, icon=icon,
                        require=require, extra=extra)

    # ------------------------------------------------------------ tareas
    def run(self, func, /, *args, on_done=None, on_error=None, on_progress=None, progress=False, label="",
            quiet=False, retry=None, count_fmt=None, **kwargs) -> Task:
        task = Task(func, *args, progress=progress, **kwargs)
        self._tasks[task] = (label, quiet)
        if label and not quiet:
            self.topbar.set_activity(label, 0.0 if progress else None)

        def finished():
            self._tasks.pop(task, None)
            busy = [(lb, q) for (lb, q) in self._tasks.values() if lb and not q]
            if busy:
                self.topbar.set_activity(busy[-1][0])
            else:
                self.topbar.set_activity(None)

        def ok(result):
            finished()
            if on_done:
                on_done(result)

        def fail(exc):
            finished()
            msg = str(exc)
            if on_error:
                on_error(msg)
            if isinstance(exc, Cancelled):
                self.toast("info", tr("Upload cancelled."))
                return
            nice = msg[:1].upper() + msg[1:]
            self.topbar.set_activity(_short_error(exc), error=True, retry=retry)
            self.toast("err", nice, tr("Retry") if retry else None, retry)

        def prog(f, m):
            if label and not quiet:
                cnt = count_fmt(f, m) if count_fmt else m
                self.topbar.set_activity(label, f, cnt)
            if on_progress:
                on_progress(f, m)

        task.signals.done.connect(ok)
        task.signals.failed.connect(fail)
        if progress or on_progress:
            task.signals.progress.connect(prog)
        self.pool.start(task)
        return task

    # ------------------------------------------------------------ conexión
    def reconnect(self):
        self.connect_device(demo=False)

    def connect_device(self, demo: bool = False, first: bool = False):
        if self.kb:
            self.kb.close()
            self.kb = None
        self.topbar.set_connection("searching")
        self.empty.set_state("searching")
        self.stack.setCurrentWidget(self.empty)
        QApplication.processEvents()
        try:
            self.kb = L75.open(demo=demo)
        except Exception as e:  # noqa: BLE001
            self._no_keyboard(e)
            return
        bus = "demo" if demo else self.kb.bus
        self.topbar.set_connection(bus, tr("simulated keyboard") if demo else ("L75 BT5.0" if bus == "bt" else "L75"))
        self.stack.setCurrentWidget(self.pages[self.current])
        self.on_connected()

    def _no_keyboard(self, exc: Exception):
        msg = str(exc)
        perm = isinstance(exc, PermissionDenied)
        rf = False
        if not perm:
            try:
                rf = any(d.bus == "dongle" for d in list_devices(include_dongles=True))
            except Exception:  # noqa: BLE001
                rf = False
        self.topbar.set_connection("rf" if rf else "none", tr("not supported yet") if rf else "")
        self.empty.set_state("udev" if perm else "none", msg)
        self.stack.setCurrentWidget(self.empty)

    def on_connected(self):
        kb = self.kb

        def work():
            info = {"profile": kb.get_profile()}
            for name, f in (("fw", kb.firmware_version), ("id", kb.device_id), ("battery", kb.battery)):
                try:
                    info[name] = f()
                except Exception:  # noqa: BLE001
                    info[name] = None
            return info

        def got(info):
            self.info = info
            p = info["profile"]
            self.profile = p if 0 <= p < 3 else 0
            self.topbar.set_profile(self.profile)
            fw = info.get("fw")
            if fw is not None and not kb.is_demo:
                sub = f"L75 · FW {fw >> 8}.{fw & 0xFF:02d}" if kb.bus == "usb" else "L75 BT5.0"
                self.topbar.set_connection(kb.bus, sub)
            if info.get("battery"):
                self.battery = info["battery"]
                self.topbar.set_battery(*info["battery"])
            for page in self.pages.values():
                page.on_connected()

        self.run(work, on_done=got, label=tr("Connecting…"), retry=self.reconnect)

    def change_profile(self, idx: int):
        if not self.kb:
            return

        def done(_):
            self.profile = idx
            self.toast("info", tr("Profile {n} loaded").format(n=idx + 1))
            for page in self.pages.values():
                page.on_profile()

        self.run(self.kb.set_profile, idx, on_done=done, label=tr("Loading profile {n}…").format(n=idx + 1),
                 retry=lambda: self.change_profile(idx))

    # ------------------------------------------------------------ otros
    def about(self):
        self.confirm("L75 Config " + __version__,
                     tr("Free (GPL-3.0) configurator for the ROYALAXE × ProtoArc L75 keyboard for Linux, Windows "
                        "and macOS.") + "<br><br>" +
                     tr("Unofficial project, not affiliated with ProtoArc or ROYALAXE. The protocol was obtained by "
                        "reading the official driver."),
                     tr("View the code"), lambda: QDesktopServices.openUrl(QUrl(REPO_URL)), icon="info",
                     cancel=tr("Close"))

    def set_language(self, code: str) -> None:
        """Cambia el idioma rehaciendo la ventana (los textos se crean al construir los widgets)."""
        apply_language(code)
        demo = bool(self.kb and self.kb.is_demo)
        if self.kb:
            self.kb.close()
            self.kb = None
        geom = self.geometry()
        new = MainWindow(demo=demo)
        new.setGeometry(geom)
        new.go(self.current)
        app = QApplication.instance()
        app._l75_window = new
        new.show()
        self.close()
        self.deleteLater()

    def closeEvent(self, ev):
        if self.kb:
            self.kb.close()
        super().closeEvent(ev)


def apply_language(code) -> str:
    """"auto" sigue el idioma del sistema (QLocale funciona también en Windows y macOS)."""
    from PySide6.QtCore import QLocale

    from ..i18n import set_language
    if not code or code == "auto":
        code = os.environ.get("L75_LANG") or ("es" if QLocale.system().name().lower().startswith("es") else "en")
    return set_language(code)


def _short_error(exc: Exception) -> str:
    if isinstance(exc, NoResponse):
        return tr("The keyboard did not answer")
    if isinstance(exc, PermissionDenied):
        return tr("Missing permission")
    return str(exc).split("\n")[0][:60]


def run(demo: bool = False, theme_mode: str | None = None, language: str | None = None) -> int:
    import sys

    from .theme import init

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("L75 Config")
    app.setDesktopFileName("l75-config")
    init(app, theme_mode)
    apply_language(language or QSettings("l75-config", "l75-config").value("language", "auto"))
    from PySide6.QtGui import QIcon

    from .theme import ASSETS
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256, 512):
        icon.addFile(str(ASSETS / "icon" / f"l75-config-{size}.png"))
    app.setWindowIcon(icon)
    w = MainWindow(demo=demo)
    app._l75_window = w
    w.show()
    return app.exec()

