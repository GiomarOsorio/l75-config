"""Prueba de humo de la interfaz: abre la ventana en modo demo y recorre las secciones."""

import os
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import QThreadPool
    from PySide6.QtWidgets import QApplication
except ImportError:  # pragma: no cover - PySide6 es opcional para las pruebas del protocolo
    QApplication = None


@unittest.skipIf(QApplication is None, "PySide6 no instalado")
class GuiSmokeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from l75ctl.ui.theme import init

        cls.app = QApplication.instance() or QApplication([])
        init(cls.app, "dark")

    def _settle(self, w, min_s=0.15, max_s=10.0):
        t0 = time.monotonic()
        while time.monotonic() - t0 < max_s:
            self.app.processEvents()
            QThreadPool.globalInstance().waitForDone(10)
            if not w._tasks and time.monotonic() - t0 > min_s:
                self.app.processEvents()
                return

    def test_demo_window(self):
        from l75ctl.keymap import KEYS, Action
        from l75ctl.ui.window import MainWindow

        w = MainWindow(demo=True)
        w.resize(1280, 800)
        w.show()
        self._settle(w)
        self.assertIsNotNone(w.kb)
        self.assertEqual(w.topbar.conn_label.text(), "Modo demo")
        for key in ("keys", "light", "colors", "macros", "screen", "settings"):
            w.go(key)
            self._settle(w)
            self.assertIs(w.stack.currentWidget(), w.pages[key])

        # reasignar una tecla desde el panel
        keys = w.pages["keys"]
        caps = next(k for k in KEYS if k.name == "CapsLock")
        keys.select_key(caps)
        keys.key_combo.setCurrentIndex(keys.key_combo.findData(0x29))
        keys.kind.setIndex(0)
        keys.apply()
        self._settle(w)
        self.assertEqual(keys.actions[caps.slot], Action.key(0x29))
        self.assertEqual(keys.kbv.labels[caps.slot].cls, "remap")

        # capa Fn: las teclas del sistema salen bloqueadas (rojo) y con su nombre real
        keys.layer.setValue(True)
        keys._layer_changed(True)
        self._settle(w)
        i_key = next(k for k in KEYS if k.name == "I")
        self.assertEqual(keys.kbv.labels[i_key.slot].cls, "locked")
        self.assertEqual(keys.kbv.labels[i_key.slot].legend, "iOS")
        self.assertIn(i_key.slot, keys.kbv.locked)
        f6 = next(k for k in KEYS if k.name == "F6")
        self.assertEqual(keys.kbv.labels[f6.slot].cls, "remap")
        keys.layer.setValue(False)
        keys._layer_changed(False)
        self._settle(w)

        # luz: elegir modo y aplicar
        light = w.pages["light"]
        light.pick_mode("breath")
        light.apply()
        self._settle(w)
        self.assertEqual(w.kb.get_light().mode, "breath")

        # cambio de tema
        from l75ctl.ui.theme import theme
        theme().set_mode("light")
        theme().set_mode("dark")
        w.close()


if __name__ == "__main__":
    unittest.main()
