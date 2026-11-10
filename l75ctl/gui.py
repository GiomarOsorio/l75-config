"""Punto de entrada de la interfaz gráfica (la implementación está en l75ctl/ui/)."""

from __future__ import annotations

import sys

from .ui import run

__all__ = ["run"]

if __name__ == "__main__":
    sys.exit(run("--demo" in sys.argv))
