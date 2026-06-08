"""
Tray-Icons für garmin-sync.

Lädt PNG-Assets aus assets/icon-master/ (vom Reviewer geliefertes finales Design)
und skaliert sie LANCZOS auf die native Tray-Größe des Monitors.

Asset-Pfad:
  • frozen (PyInstaller): sys._MEIPASS / assets / icon-master /
  • dev:                  Paket-Root  / assets / icon-master /
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image


def _asset(name: str) -> Path:
    """Absoluter Pfad zu einer Datei unter assets/ — frozen und dev."""
    base = Path(sys._MEIPASS) if getattr(sys, "frozen", False) else Path(__file__).parent.parent
    return base / "assets" / name


def _get_tray_size() -> int:
    """Native Small-Icon-Größe des Monitors (SM_CXSMICON = 49)."""
    try:
        import ctypes
        size = ctypes.windll.user32.GetSystemMetrics(49)
        if 12 <= size <= 64:
            return size
    except Exception:
        pass
    return 32


def _load_tray(status: str) -> Image.Image:
    """Lädt 256 px-PNG und skaliert LANCZOS auf native Tray-Größe."""
    size = _get_tray_size()
    src  = Image.open(_asset(f"icon-master/garmin-sync-{status}-256.png")).convert("RGBA")
    return src.resize((size, size), Image.LANCZOS)


def icon_idle()    -> Image.Image: return _load_tray("idle")
def icon_ok()      -> Image.Image: return _load_tray("ok")
def icon_syncing() -> Image.Image: return _load_tray("syncing")
def icon_error()   -> Image.Image: return _load_tray("error")
