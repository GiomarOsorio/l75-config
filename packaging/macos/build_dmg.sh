#!/usr/bin/env bash
# Construye dist/L75_Config-<version>-macOS-<arch>.dmg (en un Mac).
#   requisitos: python3 con pyinstaller, PySide6-Essentials, Pillow, hidapi (pip)
#   uso: packaging/macos/build_dmg.sh [python]
# La app no está firmada: la primera vez, clic derecho sobre "L75 Config" → Abrir.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PY="${1:-python3}"
cd "$ROOT"
VERSION="$("$PY" -c 'import l75ctl; print(l75ctl.__version__)')"
ARCH="$(uname -m)"
"$PY" -m PyInstaller --noconfirm --clean --distpath dist --workpath build packaging/l75-config.spec
STAGE="build/dmg"
rm -rf "$STAGE"
mkdir -p "$STAGE"
cp -R "dist/L75 Config.app" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
# firma ad hoc: evita el aviso de "app dañada" en Apple Silicon (no sustituye a una firma de Apple)
codesign --force --deep --sign - "$STAGE/L75 Config.app" || true
OUT="dist/L75_Config-$VERSION-macOS-$ARCH.dmg"
rm -f "$OUT"
hdiutil create -volname "L75 Config" -srcfolder "$STAGE" -ov -format UDZO "$OUT"
echo "Listo: $OUT"
