#!/bin/sh
# Lanzador dentro del Flatpak: sin argumentos abre la interfaz.
export PYTHONPATH="/app/lib/l75-config:/app/lib/python3.13/site-packages${PYTHONPATH:+:$PYTHONPATH}"
if [ $# -eq 0 ]; then
    exec python3 -m l75ctl gui
fi
exec python3 -m l75ctl "$@"
