"""Tema de L75 Config: tokens del diseño -> QSS, fuentes e iconos SVG.

Los tokens salen de assets/tokens.json (exportados de Claude Design). Los dos
temas (oscuro y claro) comparten nombres; cambiar de tema vuelve a rellenar la
plantilla QSS y avisa a los widgets pintados a mano con la señal `changed`.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from string import Template

from PySide6.QtCore import QByteArray, QObject, QPointF, QRectF, QSettings, QSize, Qt, Signal
from PySide6.QtGui import (QColor, QFont, QFontDatabase, QIcon, QLinearGradient, QPainter, QPixmap)
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication, QGraphicsDropShadowEffect, QWidget

ASSETS = Path(__file__).resolve().parent.parent / "assets"
TOKENS = json.loads((ASSETS / "tokens.json").read_text(encoding="utf-8"))

UI_FONT = "Inter"
MONO_FONT = "JetBrains Mono"
RGB_STOPS = [(0.0, "#FF4D8D"), (0.25, "#FFB547"), (0.5, "#3DF5A1"), (0.75, "#2BD2F0"), (1.0, "#8B7CFF")]


def _parse_color(s: str) -> QColor:
    m = re.match(r"rgba\((\d+),\s*(\d+),\s*(\d+),\s*([\d.]+)\)", s)
    if m:
        r, g, b = (int(m.group(i)) for i in (1, 2, 3))
        a = float(m.group(4))
        return QColor(r, g, b, round(a * 255) if a <= 1 and "." in m.group(4) else int(a))
    return QColor(s)


class Theme(QObject):
    changed = Signal()

    def __init__(self):
        super().__init__()
        self.mode = "dark"
        self._colors: dict[str, QColor] = {}
        self._qss: dict[str, str] = {}
        self._load()

    # ------------------------------------------------------------ tokens
    def _load(self):
        key = "oscuro" if self.mode == "dark" else "claro"
        raw = TOKENS["colores"][key]
        self._colors = {k: _parse_color(v["valor"]) for k, v in raw.items()}
        self._qss = {k: v["qss"] for k, v in raw.items()}

    @property
    def dark(self) -> bool:
        return self.mode == "dark"

    def c(self, name: str) -> QColor:
        return QColor(self._colors[name])

    def hex(self, name: str) -> str:
        return self._colors[name].name()

    def shadow(self, widget: QWidget, level: int = 1) -> None:
        s = TOKENS["sombras"]["oscuro" if self.dark else "claro"][f"shadow-{level}"]
        eff = QGraphicsDropShadowEffect(widget)
        eff.setOffset(s["offsetX"], s["offsetY"])
        eff.setBlurRadius(s["blurRadius"])
        eff.setColor(_parse_color(s["color"]))
        widget.setGraphicsEffect(eff)

    # ------------------------------------------------------------ aplicar
    def set_mode(self, mode: str) -> None:
        self.mode = "light" if mode == "light" else "dark"
        self._load()
        _icon_pixmap.cache_clear()
        self.apply()
        QSettings("l75-config", "l75-config").setValue("theme", self.mode)
        self.changed.emit()

    def apply(self) -> None:
        app = QApplication.instance()
        values = {k.replace("-", "_"): v for k, v in self._qss.items()}
        values["ui"] = UI_FONT
        values["mono"] = MONO_FONT
        values["check_icon"] = _check_svg_path(self.hex("on-accent"))
        values["chev"] = _chevron_svg_path(self.hex("text-2"))
        app.setStyleSheet(Template(QSS).substitute(values))

    # ------------------------------------------------------------ iconos
    def icon(self, name: str, color: str = "text-2", size: int = 16, active: str | None = None) -> QIcon:
        ic = QIcon()
        ic.addPixmap(self.pixmap(name, color, size), QIcon.Normal, QIcon.Off)
        ic.addPixmap(self.pixmap(name, "text-3", size), QIcon.Disabled, QIcon.Off)
        if active:
            ic.addPixmap(self.pixmap(name, active, size), QIcon.Normal, QIcon.On)
            ic.addPixmap(self.pixmap(name, active, size), QIcon.Active, QIcon.On)
        return ic

    def pixmap(self, name: str, color: str = "text-2", size: int = 16) -> QPixmap:
        col = color if color.startswith("#") else self.hex(color)
        dpr = QApplication.instance().devicePixelRatio() if QApplication.instance() else 1.0
        return _icon_pixmap(name, col, size, max(1.0, dpr))


THEME: Theme | None = None


def theme() -> Theme:
    global THEME
    if THEME is None:
        THEME = Theme()
    return THEME


ALIASES = json.loads((ASSETS / "icons" / "alias.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1024)
def _icon_pixmap(name: str, color: str, size: int, dpr: float) -> QPixmap:
    name = ALIASES.get(name, name)
    path = ASSETS / "icons" / f"{name}.svg"
    svg = path.read_text(encoding="utf-8").replace("currentColor", color)
    r = QSvgRenderer(QByteArray(svg.encode()))
    pm = QPixmap(round(size * dpr), round(size * dpr))
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    r.render(p)
    p.end()
    pm.setDevicePixelRatio(dpr)
    return pm


def _svg_file(name: str, svg: str) -> str:
    import tempfile

    d = Path(tempfile.gettempdir()) / "l75-config-qss"
    d.mkdir(exist_ok=True)
    f = d / name
    f.write_text(svg, encoding="utf-8")
    return f.as_posix()


def _check_svg_path(color: str) -> str:
    return _svg_file(f"check-{color[1:]}.svg",
                     f'<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" '
                     f'stroke="{color}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">'
                     f'<path d="M5 12.5l4.5 4.5L19 7.5"/></svg>')


def _chevron_svg_path(color: str) -> str:
    return _svg_file(f"chev-{color[1:]}.svg",
                     f'<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" '
                     f'stroke="{color}" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">'
                     f'<path d="M6 9l6 6l6-6"/></svg>')


def rgb_gradient(x1: float, x2: float, y: float = 0) -> QLinearGradient:
    g = QLinearGradient(QPointF(x1, y), QPointF(x2, y))
    for pos, col in RGB_STOPS:
        g.setColorAt(pos, QColor(col))
    return g


# ---------------------------------------------------------------- fuentes
def load_fonts() -> None:
    for f in sorted((ASSETS / "fonts").glob("*.ttf")):
        QFontDatabase.addApplicationFont(str(f))
    app = QApplication.instance()
    font = QFont(UI_FONT)
    font.setPixelSize(13)
    font.setHintingPreference(QFont.PreferNoHinting)
    app.setFont(font)


def font(px: float, weight: int = 400, mono: bool = False) -> QFont:
    f = QFont(MONO_FONT if mono else UI_FONT)
    f.setPixelSize(max(1, round(px)))
    f.setWeight(QFont.Weight(weight))
    return f


def init(app: QApplication, mode: str | None = None) -> Theme:
    load_fonts()
    t = theme()
    saved = QSettings("l75-config", "l75-config").value("theme", "dark")
    t.mode = mode or (saved if saved in ("dark", "light") else "dark")
    t._load()
    t.apply()
    return t


def paint_rgb_line(p: QPainter, rect: QRectF, opacity: float = 0.75) -> None:
    p.save()
    p.setOpacity(opacity)
    p.setPen(Qt.NoPen)
    p.setBrush(rgb_gradient(rect.left(), rect.right()))
    p.drawRoundedRect(rect, rect.height() / 2, rect.height() / 2)
    p.restore()


ICON_SIZE = QSize(16, 16)

# ---------------------------------------------------------------- plantilla QSS
# Selectores: cada clase de l75.css tiene su equivalente aquí (ver docs/design/HANDOFF.md).
QSS = r"""
* { font-family: "${ui}"; font-size: 13px; color: ${text_1}; outline: none; }
QMainWindow, QWidget#Root { background: ${bg}; }
QWidget#Content, QStackedWidget#Pages, QScrollArea#PageScroll, QWidget#PageBody { background: ${bg}; }
QScrollArea { border: none; background: transparent; }
QScrollArea > QWidget > QWidget { background: transparent; }
QToolTip { background: ${tooltip_bg}; color: ${tooltip_fg}; border: none; border-radius: 6px; padding: 6px 9px; font-size: 12px; }

/* ---------- tipografía ---------- */
QLabel { background: transparent; }
QLabel[role="display"] { font-size: 22px; font-weight: 600; }
QLabel[role="title"] { font-size: 16px; font-weight: 600; }
QLabel[role="sub"] { font-size: 14px; font-weight: 600; }
QLabel[role="strong"] { font-weight: 500; }
QLabel[role="body2"] { color: ${text_2}; }
QLabel[role="cap"] { font-size: 12px; color: ${text_2}; }
QLabel[role="cap3"] { font-size: 12px; color: ${text_3}; }
QLabel[role="label"] { font-size: 11px; font-weight: 600; color: ${text_2}; letter-spacing: 0.6px; }
QLabel[role="mono"] { font-family: "${mono}"; font-size: 12px; font-weight: 500; }
QLabel[role="mono2"] { font-family: "${mono}"; font-size: 12px; font-weight: 500; color: ${text_2}; }
QLabel[role="kv-l"] { color: ${text_2}; }
QLabel[role="kv-v"] { font-family: "${mono}"; font-size: 12.5px; font-weight: 500; }
QLabel[tone="error"] { color: ${error}; }
QLabel[tone="warning"] { color: ${warning}; }
QLabel[tone="success"] { color: ${success}; }
QLabel[tone="accent"] { color: ${accent}; }
QLabel[role="link"] { color: ${accent}; }
QLabel[role="kbd"] { font-family: "${mono}"; font-size: 11px; font-weight: 600; color: ${key_legend};
    background: ${key_top_1}; border: 1px solid ${key_edge}; border-bottom: 3px solid ${key_skirt};
    border-radius: 5px; padding: 1px 6px; }
QLabel[pill] { border-radius: 11px; padding: 2px 8px; font-size: 11.5px; font-weight: 600; }
QLabel[pill="neutral"] { background: ${surface_3}; color: ${text_2}; }
QLabel[pill="acc"] { background: ${accent_soft}; color: ${accent}; }
QLabel[pill="ok"] { background: ${success_soft}; color: ${success}; }
QLabel[pill="warn"] { background: ${warning_soft}; color: ${warning}; }
QLabel[pill="err"] { background: ${error_soft}; color: ${error}; }
QLabel[pill="demo"] { background: ${demo_soft}; color: ${demo}; }

/* ---------- superficies ---------- */
QFrame[card="true"] { background: ${surface_1}; border: 1px solid ${border}; border-radius: 12px; }
QFrame[card="danger"] { background: ${error_soft}; border: 1px solid ${error_line}; border-radius: 12px; }
QFrame[card="inner"] { background: ${surface_2}; border: 1px solid ${border}; border-radius: 12px; }
QFrame[divider="h"] { background: ${border}; max-height: 1px; min-height: 1px; border: none; }
QFrame[divider="v"] { background: ${border}; max-width: 1px; min-width: 1px; border: none; }
QFrame[divider="vs"] { background: ${border_strong}; max-width: 1px; min-width: 1px; border: none; }
QFrame[banner] { border-radius: 12px; border: 1px solid ${accent_line}; background: ${accent_soft}; }
QFrame[banner="ok"] { border-color: ${success_line}; background: ${success_soft}; }
QFrame[banner="warn"] { border-color: ${warning_line}; background: ${warning_soft}; }
QFrame[banner="err"] { border-color: ${error_line}; background: ${error_soft}; }
QFrame[iconbox] { border-radius: 8px; background: ${surface_2}; border: 1px solid ${border}; }
QFrame[iconbox="err"] { background: ${error_soft}; border: none; border-radius: 10px; }
QFrame[iconbox="neutral"] { background: ${surface_3}; border: none; border-radius: 10px; }
QFrame[kv="true"] { border: none; border-bottom: 1px solid ${border}; background: transparent; }
QFrame[kv="last"] { border: none; background: transparent; }
QFrame[codebox="true"] { background: ${surface_2}; border: 1px solid ${border}; border-radius: 8px; }

/* ---------- barra lateral ---------- */
QWidget#Sidebar { background: ${surface_1}; border-right: 1px solid ${border}; }
QLabel#AppName { font-size: 15px; font-weight: 600; }
QLabel#AppSub { font-size: 11px; color: ${text_2}; }
QToolButton[nav="true"] { background: transparent; border: none; border-radius: 8px; color: ${text_2};
    font-size: 13.5px; font-weight: 500; text-align: left; padding: 0 12px; min-height: 40px; max-height: 40px; }
QToolButton[nav="true"]:hover { background: ${surface_3}; color: ${text_1}; }
QToolButton[nav="true"]:checked { background: ${accent_soft}; color: ${text_1}; }
QToolButton[nav="true"]:disabled { color: ${text_3}; }
QToolButton[nav="true"]:focus { border: 2px solid ${focus}; }
QLabel#Version { font-family: "${mono}"; font-size: 11px; color: ${text_3}; }

/* ---------- barra superior ---------- */
QWidget#Topbar { background: ${bg}; border-bottom: 1px solid ${border}; }
QFrame#Conn { border-radius: 16px; border: 1px solid ${border}; background: ${surface_1}; }
QFrame#Conn[state="demo"] { border-color: ${demo_line}; background: ${demo_soft}; }
QFrame#Conn[state="err"] { border-color: ${error_line}; background: ${error_soft}; }
QFrame#Conn[state="rf"] { border-color: ${warning_line}; background: ${warning_soft}; }
QLabel#ConnLabel { font-weight: 500; }
QLabel#ConnSub { font-family: "${mono}"; font-size: 11.5px; color: ${text_2}; }
QLabel#ActLabel { font-size: 12.5px; color: ${text_2}; }
QLabel#ActLabel[state="busy"] { color: ${text_1}; }
QLabel#ActLabel[state="err"] { color: ${error}; }
QLabel#ActCount { font-family: "${mono}"; font-size: 11.5px; color: ${text_2}; }
QLabel#Batt { font-family: "${mono}"; font-size: 12px; color: ${text_2}; }

/* ---------- botones ---------- */
QPushButton { height: 30px; min-height: 30px; max-height: 30px; padding: 0 14px; border-radius: 8px; border: 1px solid ${border_strong};
    background: ${surface_3}; color: ${text_1}; font-weight: 500; }
QPushButton:hover { background: ${surface_4}; }
QPushButton:pressed { background: ${surface_2}; }
QPushButton:focus { border: 2px solid ${focus}; }
QPushButton:disabled { background: ${surface_2}; border-color: ${border}; color: ${text_3}; }
QPushButton[variant="primary"] { background: ${accent}; border-color: ${accent}; color: ${on_accent}; }
QPushButton[variant="primary"]:hover { background: ${accent_hover}; border-color: ${accent_hover}; }
QPushButton[variant="primary"]:pressed { background: ${accent_pressed}; border-color: ${accent_pressed}; }
QPushButton[variant="primary"]:focus { border: 2px solid ${focus}; }
QPushButton[variant="primary"]:disabled { background: ${surface_2}; border-color: ${border}; color: ${text_3}; }
QPushButton[variant="danger"] { background: ${error_soft}; border-color: ${error_line}; color: ${error}; }
QPushButton[variant="danger"]:hover { background: ${error_soft_2}; }
QPushButton[variant="danger"]:pressed { border-color: ${error}; }
QPushButton[variant="danger"]:disabled { background: ${surface_2}; border-color: ${border}; color: ${text_3}; }
QPushButton[variant="danger-solid"] { background: ${error_solid}; border-color: ${error_solid}; color: ${on_error}; }
QPushButton[variant="danger-solid"]:hover { background: ${error_solid_hover}; }
QPushButton[variant="danger-solid"]:disabled { background: ${surface_2}; border-color: ${border}; color: ${text_3}; }
QPushButton[variant="ghost"] { background: transparent; border-color: transparent; color: ${text_2}; }
QPushButton[variant="ghost"]:hover { background: ${surface_3}; color: ${text_1}; }
QPushButton[variant="ghost"]:pressed { background: ${surface_2}; }
QPushButton[variant="ghost"]:focus { border: 2px solid ${focus}; }
QPushButton[variant="ghost"]:disabled { background: transparent; border-color: transparent; color: ${text_3}; }
QPushButton[variant="rec-on"] { background: ${error_soft}; border-color: ${error_line}; color: ${error}; }
QPushButton[size="sm"] { height: 26px; min-height: 26px; max-height: 26px; padding: 0 10px; font-size: 12px; border-radius: 6px; }
QPushButton[size="lg"] { height: 38px; min-height: 38px; max-height: 38px; padding: 0 18px; font-size: 14px; }
QPushButton[icononly="true"] { padding: 0; min-width: 30px; max-width: 30px; }
QPushButton[size="sm"][icononly="true"] { min-width: 26px; max-width: 26px; }
QPushButton[variant="link"] { background: transparent; border: none; color: ${accent}; padding: 0 2px; font-weight: 500; }
QPushButton[variant="link"]:hover { color: ${accent_hover}; }

/* ---------- control segmentado ---------- */
QFrame[seg="true"] { background: ${surface_2}; border: 1px solid ${border}; border-radius: 8px; }
QFrame[seg="true"] QToolButton { background: transparent; border: 1px solid transparent; border-radius: 6px; color: ${text_2};
    font-size: 12.5px; font-weight: 500; min-height: 26px; max-height: 26px; padding: 0 10px; }
QFrame[seg="true"] QToolButton:hover { color: ${text_1}; background: ${surface_3}; }
QFrame[seg="true"] QToolButton:checked { background: ${seg_on}; border-color: ${border_strong}; color: ${text_1}; }
QFrame[seg="true"] QToolButton:disabled { color: ${text_3}; background: transparent; border-color: transparent; }
QFrame[seg="true"] QToolButton[mono="true"] { font-family: "${mono}"; font-size: 12.5px; }
QFrame[seg="zone"] { background: ${surface_1}; border: 1px solid ${border}; border-radius: 10px; }
QFrame[seg="zone"] QToolButton { background: transparent; border: 1px solid transparent; border-radius: 8px; text-align: left;
    min-height: 44px; max-height: 44px; padding: 0 14px; }
QFrame[seg="zone"] QToolButton:hover { background: ${surface_2}; }
QFrame[seg="zone"] QToolButton:checked { background: ${seg_on}; border-color: ${border_strong}; }

/* ---------- chips de perfil ---------- */
QToolButton[chip="true"] { min-width: 28px; min-height: 26px; max-height: 26px; padding: 0 6px; border-radius: 6px; border: 1px solid transparent;
    background: transparent; color: ${text_2}; font-family: "${mono}"; font-size: 12.5px; font-weight: 600; }
QToolButton[chip="true"]:hover { background: ${surface_3}; color: ${text_1}; }
QToolButton[chip="true"]:checked { background: ${accent_soft}; border-color: ${accent_line}; color: ${accent}; }
QToolButton[chip="true"]:disabled { color: ${text_3}; background: transparent; border-color: transparent; }

/* ---------- campos ---------- */
QLineEdit, QPlainTextEdit, QTextEdit { background: ${surface_2}; border: 1px solid ${border}; border-radius: 8px; color: ${text_1};
    padding: 0 10px; selection-background-color: ${accent}; selection-color: ${on_accent}; }
QLineEdit { min-height: 30px; max-height: 30px; }
QPlainTextEdit { padding: 8px 10px; font-family: "${mono}"; font-size: 12.5px; }
QLineEdit:hover, QPlainTextEdit:hover { border-color: ${border_strong}; }
QLineEdit:focus, QPlainTextEdit:focus { border-color: ${accent}; }
QLineEdit:disabled, QPlainTextEdit:disabled { color: ${text_3}; background: ${surface_1}; }
QLineEdit[error="true"], QPlainTextEdit[error="true"] { border-color: ${error}; }
QLineEdit[mono="true"] { font-family: "${mono}"; font-size: 12.5px; }

QFrame[num="true"] { background: ${surface_2}; border: 1px solid ${border}; border-radius: 8px; }
QFrame[num="true"]:hover { border-color: ${border_strong}; }
QFrame[num="true"][focus="true"] { border-color: ${accent}; }
QFrame[num="true"][error="true"] { border-color: ${error}; }
QFrame[num="true"] QToolButton { background: transparent; border: none; color: ${text_2}; min-width: 28px; max-width: 28px; min-height: 28px; }
QFrame[num="true"] QToolButton:hover { background: ${surface_3}; color: ${text_1}; }
QFrame[num="true"] QToolButton:disabled { background: transparent; }
QFrame[num="true"] QLineEdit { background: transparent; border: none; padding: 0; min-height: 28px; max-height: 28px;
    font-family: "${mono}"; font-size: 12.5px; font-weight: 500; }
QFrame[num="true"] QLabel { color: ${text_2}; font-size: 12px; padding-right: 8px; }

QComboBox { min-height: 30px; max-height: 30px; padding: 0 8px 0 10px; background: ${surface_2}; border: 1px solid ${border};
    border-radius: 8px; color: ${text_1}; }
QComboBox:hover { border-color: ${border_strong}; }
QComboBox:focus, QComboBox:on { border-color: ${accent}; }
QComboBox:disabled { color: ${text_3}; background: ${surface_1}; }
QComboBox::drop-down { border: none; width: 24px; subcontrol-origin: padding; subcontrol-position: center right; }
QComboBox::down-arrow { image: url("${chev}"); width: 16px; height: 16px; }
QComboBox QAbstractItemView { background: ${surface_3}; border: 1px solid ${border_strong}; border-radius: 8px; padding: 4px;
    outline: none; selection-background-color: ${accent_soft}; selection-color: ${accent}; }
QComboBox QAbstractItemView::item { min-height: 30px; padding: 0 10px; border-radius: 6px; color: ${text_1}; }
QComboBox QAbstractItemView::item:hover { background: ${surface_4}; }
QComboBox QAbstractItemView::item:selected { background: ${accent_soft}; color: ${accent}; }
QComboBox QLineEdit { background: transparent; border: none; padding: 0; min-height: 26px; }
QComboBox[kbd="true"] { min-height: 20px; max-height: 20px; padding: 0 4px 0 6px; font-family: "${mono}"; font-size: 11.5px;
    font-weight: 600; color: ${key_legend}; background: ${key_top_1}; border: 1px solid ${key_edge};
    border-bottom: 3px solid ${key_skirt}; border-radius: 5px; }
QComboBox[kbd="true"]:hover { border-color: ${key_hover_edge}; border-bottom-color: ${key_skirt}; }
QComboBox[kbd="true"]::drop-down { width: 0; border: none; }
QComboBox[kbd="true"]::down-arrow { image: none; width: 0; height: 0; }
QComboBox[kbd="true"] QLineEdit { font-family: "${mono}"; font-size: 11.5px; font-weight: 600; color: ${key_legend}; min-height: 18px; }

QMenu { background: ${surface_3}; border: 1px solid ${border_strong}; border-radius: 8px; padding: 4px; }
QMenu::item { min-height: 30px; padding: 0 12px 0 10px; border-radius: 6px; color: ${text_1}; }
QMenu::item:selected { background: ${surface_4}; }
QMenu::separator { height: 1px; background: ${border}; margin: 4px 6px; }
QMenu::icon { padding-left: 8px; }

/* ---------- listas ---------- */
QListWidget { background: transparent; border: none; outline: none; }
QListWidget::item { border: none; padding: 0; margin: 0; background: transparent; }
QListWidget::item:selected { background: transparent; }

/* ---------- barras de desplazamiento ---------- */
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: ${border_strong}; border-radius: 3px; min-height: 30px; margin: 0 2px; }
QScrollBar::handle:vertical:hover { background: ${text_3}; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle:horizontal { background: ${border_strong}; border-radius: 3px; min-width: 30px; margin: 2px 0; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }

/* ---------- progreso ---------- */
QProgressBar { background: ${track}; border: none; border-radius: 2px; max-height: 4px; min-height: 4px; text-align: center; color: transparent; }
QProgressBar::chunk { background: ${accent}; border-radius: 2px; }
QProgressBar[tone="warn"]::chunk { background: ${warning}; }
QProgressBar[tone="err"]::chunk { background: ${error}; }

/* ---------- macros ---------- */
QFrame[macroitem] { border-radius: 8px; border: 1px solid transparent; background: transparent; }
QFrame[macroitem]:hover { background: ${surface_2}; }
QFrame[macroitem="on"] { background: ${surface_3}; border-color: ${border_strong}; }
QLabel[mlidx] { min-width: 28px; max-width: 28px; min-height: 22px; max-height: 22px; border-radius: 6px; qproperty-alignment: AlignCenter;
    font-family: "${mono}"; font-size: 11px; font-weight: 600; background: ${surface_3}; color: ${text_3}; }
QLabel[mlidx="used"] { background: ${accent_soft}; color: ${accent}; }
QLabel[mlt="empty"] { color: ${text_3}; }
QLabel[mlt="used"] { font-weight: 500; }
QFrame[ev="true"] { border-radius: 8px; border: 1px solid transparent; background: transparent; }
QFrame[ev="true"]:hover { background: ${surface_2}; border-color: ${border}; }
QFrame[evic] { border-radius: 7px; min-width: 26px; max-width: 26px; min-height: 26px; max-height: 26px; }
QFrame[evic="down"] { background: ${accent_soft}; }
QFrame[evic="up"] { background: ${surface_3}; }
QFrame[evic="wait"] { background: ${warning_soft}; }
QFrame[evic="mouse"] { background: ${success_soft}; }
QFrame[evguide="true"] { border: none; border-left: 1px solid ${border_strong}; background: transparent; }

/* ---------- diálogo y toast ---------- */
QWidget#Scrim { background: ${scrim}; }
QFrame#Dialog { background: ${surface_2}; border: 1px solid ${border_strong}; border-radius: 16px; }
QFrame#Toast { background: ${surface_3}; border: 1px solid ${border_strong}; border-radius: 12px; }
QFrame#Toast QLabel#ToastText { font-weight: 500; }
QFrame#Popover { background: ${surface_3}; border: 1px solid ${border_strong}; border-radius: 12px; }

QCheckBox { spacing: 8px; }
QCheckBox::indicator { width: 16px; height: 16px; border-radius: 4px; border: 1px solid ${border_strong}; background: ${surface_2}; }
QCheckBox::indicator:checked { background: ${accent}; border-color: ${accent}; image: url("${check_icon}"); }
"""
