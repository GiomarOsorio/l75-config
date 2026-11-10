#!/usr/bin/env bash
# Instala L75 Config para el usuario actual:
#   - comprueba dependencias (python3-hid, PySide6, Pillow)
#   - instala la regla udev (pide sudo)
#   - crea el comando ~/.local/bin/l75 y un acceso directo en el menu
set -euo pipefail
DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"

echo "== Dependencias"
missing=()
python3 -c "import hid" 2>/dev/null || missing+=("python3-hid hidapi")
python3 -c "import PySide6" 2>/dev/null || missing+=("python3-pyside6")
python3 -c "import PIL" 2>/dev/null || missing+=("python3-pillow")
if [ ${#missing[@]} -gt 0 ]; then
    echo "Faltan: ${missing[*]}"
    echo "Instala con:  sudo dnf install ${missing[*]}"
    echo "(o con pip:   pip install --user hid PySide6 Pillow)"
    exit 1
fi
echo "OK"

echo "== Regla udev (acceso al teclado sin root)"
if [ ! -f /etc/udev/rules.d/70-royalaxe-l75.rules ] || ! cmp -s "$DIR/udev/70-royalaxe-l75.rules" /etc/udev/rules.d/70-royalaxe-l75.rules; then
    sudo install -m 0644 "$DIR/udev/70-royalaxe-l75.rules" /etc/udev/rules.d/70-royalaxe-l75.rules
    sudo udevadm control --reload-rules
    sudo udevadm trigger --subsystem-match=hidraw
    echo "Instalada. Desconecta y vuelve a conectar el teclado."
else
    echo "Ya instalada"
fi

echo "== Comando 'l75'"
mkdir -p "$HOME/.local/bin"
ln -sf "$DIR/l75" "$HOME/.local/bin/l75"
chmod +x "$DIR/l75"
echo "Enlace: ~/.local/bin/l75 -> $DIR/l75"

echo "== Acceso directo en el menu"
mkdir -p "$HOME/.local/share/applications"
cat > "$HOME/.local/share/applications/l75-config.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=L75 Config
Comment=Configurar teclado ROYALAXE / ProtoArc L75
Exec=$DIR/l75
Icon=input-keyboard
Terminal=false
Categories=Settings;HardwareSettings;
EOF
echo "Listo. Abre 'L75 Config' desde el menu o ejecuta: l75"
