"""Translations. The source strings are English; `es` holds the Spanish catalog.

    from l75ctl.i18n import t
    t("Keys")                         -> "Teclas" when the language is Spanish
    t("{n} remapped").format(n=3)

Language: `set_language("en" | "es" | "auto")`. "auto" follows the system
(L75_LANG, LC_ALL, LC_MESSAGES, LANG, or the OS locale).
"""

from __future__ import annotations

import locale
import os

LANGUAGES = {"en": "English", "es": "Español"}
_lang = "en"


def system_language() -> str:
    for var in ("L75_LANG", "LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE"):
        v = os.environ.get(var, "")
        if v and v not in ("C", "POSIX"):
            return "es" if v.lower().startswith("es") else "en"
    try:
        loc = locale.getlocale()[0] or ""
    except ValueError:
        loc = ""
    return "es" if loc.lower().startswith(("es", "spanish")) else "en"


def set_language(lang: str | None) -> str:
    global _lang
    if not lang or lang == "auto":
        lang = system_language()
    _lang = lang if lang in LANGUAGES else "en"
    return _lang


def language() -> str:
    return _lang


def t(text: str) -> str:
    if _lang == "en":
        return text
    from .i18n_es import ES

    return ES.get(text, text)


set_language(os.environ.get("L75_LANG") or "auto")
