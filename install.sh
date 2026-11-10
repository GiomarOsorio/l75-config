#!/usr/bin/env bash
# Installs L75 Config for the current user:
#   - checks dependencies (python3-hid, PySide6, Pillow)
#   - installs the udev rule (asks for sudo)
#   - creates the ~/.local/bin/l75 command and a menu entry
set -euo pipefail
DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"

echo "== Dependencies"
missing=()
python3 -c "import hid" 2>/dev/null || missing+=("python3-hid hidapi")
python3 -c "import PySide6" 2>/dev/null || missing+=("python3-pyside6")
python3 -c "import PIL" 2>/dev/null || missing+=("python3-pillow")
if [ ${#missing[@]} -gt 0 ]; then
    echo "Missing: ${missing[*]}"
    echo "Install with:  sudo dnf install ${missing[*]}"
    echo "(or with pip: pip install --user hidapi PySide6-Essentials Pillow)"
    exit 1
fi
echo "OK"

echo "== udev rule (keyboard access without root)"
if [ ! -f /etc/udev/rules.d/70-royalaxe-l75.rules ] || ! cmp -s "$DIR/udev/70-royalaxe-l75.rules" /etc/udev/rules.d/70-royalaxe-l75.rules; then
    sudo install -m 0644 "$DIR/udev/70-royalaxe-l75.rules" /etc/udev/rules.d/70-royalaxe-l75.rules
    sudo udevadm control --reload-rules
    sudo udevadm trigger --subsystem-match=hidraw
    echo "Installed. Unplug and reconnect the keyboard."
else
    echo "Already installed"
fi

echo "== 'l75' command"
mkdir -p "$HOME/.local/bin"
ln -sf "$DIR/l75" "$HOME/.local/bin/l75"
chmod +x "$DIR/l75"
echo "Link: ~/.local/bin/l75 -> $DIR/l75"

echo "== Menu entry"
mkdir -p "$HOME/.local/share/applications"
cat > "$HOME/.local/share/applications/l75-config.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=L75 Config
Comment=Configure the ROYALAXE / ProtoArc L75 keyboard
Comment[es]=Configura el teclado ROYALAXE / ProtoArc L75
Exec=$DIR/l75
Icon=input-keyboard
Terminal=false
Categories=Settings;HardwareSettings;
EOF
echo "Done. Open 'L75 Config' from the menu or run: l75"
