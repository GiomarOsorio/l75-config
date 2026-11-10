"""Translations: every string passed to t()/tr() has a Spanish entry with the same placeholders."""

import ast
import pathlib
import re
import unittest

from l75ctl import i18n, keymap, lighting
from l75ctl.i18n_es import ES

ROOT = pathlib.Path(__file__).resolve().parent.parent / "l75ctl"
PLACEHOLDER = re.compile(r"\{(\w*)\}")


def _literals():
    found = {}
    for f in sorted(ROOT.rglob("*.py")):
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for n in ast.walk(tree):
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in ("t", "_t", "tr")
                    and n.args and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str)):
                found.setdefault(n.args[0].value, f"{f.relative_to(ROOT)}:{n.lineno}")
    return found


def _table_strings():
    """Labels kept in tables and translated with t(variable)."""
    from l75ctl.ui import window
    from l75ctl.ui.pages import common, keys, macros, screen, settings

    out = [lab for _k, lab, _b in keymap.FUNCTIONS + keymap.MOUSE]
    out += list(keymap.MACRO_MODE_LABELS.values())
    out += [s for short, desc, _c in keymap.SYSTEM_FUNCTIONS.values() for s in (short, desc)]
    out += [m.label for m in lighting.MODES + lighting.SIDE_MODES]
    out += [name for _k, name, _i in window.SECTIONS]
    out += [x for text, _i in keys.KINDS for x in (text,)]
    out += [x for lab, _c, tip in keys.MACRO_MODES for x in (lab, tip)]
    out += list(keys.FUNC_SHORT.values()) + list(macros.MOUSE_LABELS.values())
    out += [x for text, _k, _i, hint in screen.FITS for x in (text, hint)]
    out += [x for _k, _i, title, desc in settings.OPTIONS for x in (title, desc)] + [n for _k, n in settings.INFO]
    out += list(common._MODE_HINTS.values()) + list(common._OPTION_NAMES.values()) + list(common._COLOR_NAMES.values())
    out += ["charging", "discharging", "charged"]
    return out


class I18nTest(unittest.TestCase):
    def tearDown(self):
        i18n.set_language("en")

    def test_every_literal_is_translated(self):
        missing = {s: where for s, where in _literals().items() if s not in ES}
        self.assertEqual(missing, {}, "strings without a Spanish translation")

    def test_table_strings_are_translated(self):
        try:
            import PySide6  # noqa: F401
        except ImportError:
            self.skipTest("PySide6 not installed")
        missing = [s for s in _table_strings() if s not in ES]
        self.assertEqual(missing, [])

    def test_placeholders_match(self):
        for en, es in ES.items():
            self.assertEqual(sorted(PLACEHOLDER.findall(en)), sorted(PLACEHOLDER.findall(es)), en)

    def test_switch_language(self):
        i18n.set_language("es")
        self.assertEqual(i18n.t("Keys"), "Teclas")
        self.assertEqual(keymap.Action((10, 5, 2, 0)).describe(), "Distribución iOS")
        i18n.set_language("en")
        self.assertEqual(i18n.t("Keys"), "Keys")
        self.assertEqual(keymap.Action((10, 5, 2, 0)).describe(), "iOS layout")
        self.assertEqual(i18n.set_language("fr"), "en")


if __name__ == "__main__":
    unittest.main()
