"""Pantallas sin teclado: buscando, no encontrado y falta permiso (udev)."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import QFrame, QWidget

from .. import widgets as W
from ..keyboard_view import KeyboardView
from ..theme import font
from ..window import Page

RULES = "70-royalaxe-l75.rules"
_LOCAL_RULES = Path(__file__).resolve().parents[3] / "udev" / RULES
RULES_URL = f"https://raw.githubusercontent.com/GiomarOsorio/l75-config/main/udev/{RULES}"
if _LOCAL_RULES.exists():  # ejecutando desde la carpeta del proyecto
    UDEV_CMDS = (f'sudo cp "{_LOCAL_RULES}" /etc/udev/rules.d/\n'
                 "sudo udevadm control --reload-rules && sudo udevadm trigger")
else:  # AppImage, Flatpak u otros paquetes
    UDEV_CMDS = (f"curl -fsSL {RULES_URL} | sudo tee /etc/udev/rules.d/{RULES}\n"
                 "sudo udevadm control --reload-rules && sudo udevadm trigger")
README_URL = "https://github.com/GiomarOsorio/l75-config#soluci%C3%B3n-de-problemas"


def _option(icon: str, title: str, desc: str) -> QFrame:
    f = QFrame()
    f.setProperty("card", "true")
    W.hbox(W.icon_label(icon, "text-2", 16), W.vbox(W.label(title, "strong"), W.label(desc, "cap"), spacing=2),
           "stretch", spacing=14, margins=(16, 12, 16, 12), parent=f)
    return f


class NoKeyboardPage(Page):
    def __init__(self, win):
        super().__init__(win)
        self.kbv = KeyboardView(mode="outline", deck=False)
        self.kbv.setFixedSize(456, 190)
        self.kbv.pad = (8, 8, 8, 8)
        self.title = W.label("", "display")
        self.title.setAlignment(Qt.AlignCenter)
        self.text = W.label("", "body2", wrap=True)
        self.text.setAlignment(Qt.AlignCenter)

        # sin teclado
        self.none_box = QWidget()
        W.vbox(_option("cable", "Por cable", "Bien conectado y con el interruptor del teclado en modo cable."),
               _option("inalambrico", "Por Bluetooth", "Emparejado y conectado como «L75 BT5.0»."),
               _option("receptor", "Receptor 2.4 GHz", "Todavía no está soportado: usa cable o Bluetooth."),
               spacing=8, parent=self.none_box)

        # permiso udev
        self.udev_box = QWidget()
        self.udev_banner = W.Banner("err", "<b>No pude abrir el teclado: falta permiso.</b> Linux necesita una regla "
                                           "udev para usar el L75 sin ser root.")
        code = QFrame()
        code.setProperty("codebox", True)
        lbl = W.label(UDEV_CMDS)
        lbl.setFont(font(12, 400, mono=True))
        lbl.setMinimumHeight(40)
        lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        W.vbox(lbl, margins=(12, 10, 12, 10), parent=code)
        copy = W.button("Copiar", "ghost", "copiar", size="sm", on_click=self._copy)
        W.vbox(self.udev_banner, 10,
               W.hbox(W.label("Instala la regla y recarga udev", "strong"), "stretch", copy),
               code,
               W.label("Después desconecta y vuelve a conectar el teclado (por Bluetooth, desconéctalo y conéctalo "
                       "de nuevo). Solo hace falta una vez.", "cap", wrap=True),
               spacing=8, parent=self.udev_box)
        self.err_detail = W.label("", "cap", wrap=True)
        self.err_detail.setTextInteractionFlags(Qt.TextSelectableByMouse)

        self.b_retry = W.button("Reintentar", "primary", "reintentar", on_click=win.reconnect)
        self.b_demo = W.button("Probar en modo demo", "secondary", "demo",
                               on_click=lambda: win.connect_device(demo=True))
        self.b_help = W.button("Ver instrucciones", "secondary", "externo",
                               on_click=lambda: QDesktopServices.openUrl(QUrl(README_URL)))
        col = QWidget()
        col.setFixedWidth(620)
        W.vbox(W.hbox("stretch", self.kbv, "stretch"), 14, self.title, self.text, 14, self.none_box, self.udev_box,
               self.err_detail, 12, W.hbox("stretch", self.b_retry, self.b_demo, self.b_help, "stretch", spacing=8),
               spacing=6, parent=col)
        self.lay.addStretch(1)
        self.lay.addWidget(col, 0, Qt.AlignHCenter)
        self.lay.addStretch(2)

    def set_state(self, state: str, msg: str = ""):
        searching = state == "searching"
        self.kbv.mode = "scan" if searching else "outline"
        if searching:
            self.kbv._timer.start(33)
        else:
            self.kbv._timer.stop()
        self.kbv.update()
        if searching:
            self.title.setText("Buscando tu L75…")
            self.text.setText("Un momento: miro el cable USB-C y los dispositivos Bluetooth.")
        elif state == "udev":
            self.title.setText("")
            self.text.setText("")
        else:
            self.title.setText("No encuentro tu L75")
            self.text.setText("Conéctalo con el cable USB-C o empareja «L75 BT5.0» por Bluetooth y pulsa Reintentar.")
        self.title.setVisible(state != "udev")
        self.text.setVisible(state != "udev")
        self.none_box.setVisible(state == "none")
        self.udev_box.setVisible(state == "udev" and sys.platform.startswith("linux"))
        detail = msg.split("\n")[0] if (state == "udev" and not sys.platform.startswith("linux")) else ""
        self.err_detail.setText(detail)
        self.err_detail.setVisible(bool(detail))
        for b in (self.b_retry, self.b_demo):
            b.setVisible(not searching)
        self.b_help.setVisible(state == "udev")
        self.b_demo.setVisible(state == "none")

    def _copy(self):
        QGuiApplication.clipboard().setText(UDEV_CMDS)
        self.win.toast("ok", "Comandos copiados")
