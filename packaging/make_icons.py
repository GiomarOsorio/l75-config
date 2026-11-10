"""Genera el icono de L75 Config (PNG, ICO y ICNS) a partir del logo del diseño.

Uso: QT_QPA_PLATFORM=offscreen python3 packaging/make_icons.py
"""

import sys
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QGuiApplication, QImage, QLinearGradient, QPainter, QPen

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "l75ctl" / "assets" / "icon"
STOPS = [(0.0, "#FF4D8D"), (0.25, "#FFB547"), (0.5, "#3DF5A1"), (0.75, "#2BD2F0"), (1.0, "#8B7CFF")]


def render(size: int) -> QImage:
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.TextAntialiasing)
    s = size / 512
    r = QRectF(24 * s, 24 * s, 464 * s, 464 * s)
    bg = QLinearGradient(r.topLeft(), r.bottomLeft())
    bg.setColorAt(0, QColor("#1F242B"))
    bg.setColorAt(1, QColor("#0B0D10"))
    p.setPen(QPen(QColor("#363E49"), max(1.0, 6 * s)))
    p.setBrush(bg)
    p.drawRoundedRect(r, 104 * s, 104 * s)
    f = QFont("JetBrains Mono")
    f.setPixelSize(round(220 * s))
    f.setWeight(QFont.Bold)
    p.setFont(f)
    p.setPen(QColor("#E8ECF1"))
    p.drawText(QRectF(0, 40 * s, size, 330 * s), Qt.AlignCenter, "75")
    line = QRectF(132 * s, 372 * s, 248 * s, 28 * s)
    g = QLinearGradient(line.topLeft(), line.topRight())
    for pos, col in STOPS:
        g.setColorAt(pos, QColor(col))
    p.setPen(Qt.NoPen)
    p.setBrush(g)
    p.drawRoundedRect(line, 14 * s, 14 * s)
    p.end()
    return img


def main() -> int:
    app = QGuiApplication(sys.argv)  # noqa: F841
    for f in (ROOT / "l75ctl" / "assets" / "fonts").glob("*.ttf"):
        QFontDatabase.addApplicationFont(str(f))
    OUT.mkdir(parents=True, exist_ok=True)
    for size in (16, 24, 32, 48, 64, 128, 256, 512, 1024):
        render(size).save(str(OUT / f"l75-config-{size}.png"))
    render(512).save(str(OUT / "l75-config.png"))
    from PIL import Image

    big = Image.open(OUT / "l75-config-1024.png")
    big.save(OUT / "l75-config.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    big.save(OUT / "l75-config.icns")
    print("iconos en", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
