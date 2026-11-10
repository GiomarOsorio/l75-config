"""Punto de entrada de los paquetes (PyInstaller): sin argumentos abre la interfaz."""

import sys

from l75ctl.cli import main

if __name__ == "__main__":
    # macOS puede pasar -psn_X_Y al abrir la app desde el Finder
    argv = [a for a in sys.argv[1:] if not a.startswith("-psn_")]
    sys.exit(main(argv or ["gui"]))
