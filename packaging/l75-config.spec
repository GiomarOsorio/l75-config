# PyInstaller: L75 Config (Windows, macOS y Linux).
#   pyinstaller --noconfirm packaging/l75-config.spec
# Resultado: dist/L75 Config/ (Windows/Linux) o dist/L75 Config.app (macOS).
import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent
sys.path.insert(0, str(ROOT))
from l75ctl import __version__  # noqa: E402

ICON = ROOT / "l75ctl" / "assets" / "icon"
icon = str(ICON / ("l75-config.icns" if sys.platform == "darwin" else "l75-config.ico"))
hidden = ["hidraw"] if sys.platform.startswith("linux") else ["hid"]

a = Analysis(
    [str(ROOT / "packaging" / "entry.py")],
    pathex=[str(ROOT)],
    datas=[(str(ROOT / "l75ctl" / "assets"), "l75ctl/assets")],
    hiddenimports=hidden + ["l75ctl.ui", "l75ctl.ui.pages", "PySide6.QtSvg"],
    excludes=["tkinter", "PySide6.QtWebEngineCore", "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtNetwork",
              "PySide6.QtPdf", "PySide6.QtMultimedia", "PySide6.Qt3DCore"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="l75-config",
    console=False,
    icon=icon,
    version=None,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="L75 Config")

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="L75 Config.app",
        icon=icon,
        bundle_identifier="io.github.giomarosorio.L75Config",
        version=__version__,
        info_plist={
            "CFBundleName": "L75 Config",
            "CFBundleDisplayName": "L75 Config",
            "CFBundleShortVersionString": __version__,
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "11.0",
            "NSHumanReadableCopyright": "GPL-3.0 · proyecto no oficial",
        },
    )
