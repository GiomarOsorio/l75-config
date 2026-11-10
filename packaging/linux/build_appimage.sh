#!/usr/bin/env bash
# Construye dist/L75_Config-<version>-x86_64.AppImage
#   requisitos: python3 con pyinstaller, PySide6-Essentials, Pillow, hidapi (pip)
#   uso: packaging/linux/build_appimage.sh [python]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PY="${1:-python3}"
cd "$ROOT"
VERSION="$("$PY" -c 'import l75ctl; print(l75ctl.__version__)')"
ARCH="$(uname -m)"
APPID=io.github.giomarosorio.L75Config

"$PY" -m PyInstaller --noconfirm --clean --distpath dist --workpath build packaging/l75-config.spec

APPDIR="build/AppDir"
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/lib/l75-config" "$APPDIR/usr/share/applications" \
         "$APPDIR/usr/share/metainfo" "$APPDIR/usr/share/icons/hicolor/256x256/apps" \
         "$APPDIR/usr/share/l75-config"
cp -a "dist/L75 Config/." "$APPDIR/usr/lib/l75-config/"
cp packaging/linux/$APPID.desktop "$APPDIR/usr/share/applications/"
cp packaging/linux/$APPID.desktop "$APPDIR/"
cp packaging/linux/$APPID.metainfo.xml "$APPDIR/usr/share/metainfo/"
cp l75ctl/assets/icon/l75-config-256.png "$APPDIR/usr/share/icons/hicolor/256x256/apps/$APPID.png"
cp l75ctl/assets/icon/l75-config-256.png "$APPDIR/$APPID.png"
cp udev/70-royalaxe-l75.rules "$APPDIR/usr/share/l75-config/"
cat > "$APPDIR/AppRun" <<'RUN'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/lib/l75-config/l75-config" "$@"
RUN
chmod +x "$APPDIR/AppRun"

TOOL="${APPIMAGETOOL:-}"
if [ -z "$TOOL" ]; then
    TOOL="build/appimagetool-$ARCH.AppImage"
    if [ ! -x "$TOOL" ]; then
        curl -fsSL -o "$TOOL" \
            "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-$ARCH.AppImage"
        chmod +x "$TOOL"
    fi
fi
OUT="dist/L75_Config-$VERSION-$ARCH.AppImage"
ARCH="$ARCH" APPIMAGE_EXTRACT_AND_RUN=1 "$TOOL" --no-appstream "$APPDIR" "$OUT"
echo "Listo: $OUT"
