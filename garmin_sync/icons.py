"""
Tray-Icons und App-Icon für garmin-sync.

Design: lila Außenkreis (#7c4dca) mit zwei weißen Sync-Pfeilen, innere
Statusscheibe mit weißem Puls-Zacken (EKG). Vier Varianten (idle/ok/syncing/error).

Anti-Aliasing via 4×-Supersampeln (Pillow).

Aufruf zur Regenerierung der .ico-Datei:
    python -m garmin_sync.icons
    # oder direkt:
    .venv\\Scripts\\python garmin_sync/icons.py
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw

_LILA = (0x7C, 0x4D, 0xCA, 255)
_WHITE = (255, 255, 255, 255)
_STATUS: dict[str, tuple[int, int, int, int]] = {
    "idle":    (0x88, 0x93, 0xA5, 255),  # grau — bereit
    "ok":      (0x0A, 0x8A, 0x5F, 255),  # grün — OK
    "syncing": (0xE8, 0x92, 0x3C, 255),  # orange — läuft
    "error":   (0xD6, 0x45, 0x45, 255),  # rot — Fehler
}

_SUPER = 4  # Supersample-Faktor für Anti-Aliasing


def _render(status: str, size: int) -> Image.Image:
    S = size * _SUPER
    cx = cy = S // 2

    m = max(S // 16, 1)   # Außenrand
    r_out = S // 2 - m    # Außenkreis-Radius
    r_in  = r_out // 2    # Innenkreis-Radius (Statusfarbe)
    r_arr = (r_out + r_in + 1) // 2  # Radius der Sync-Pfeil-Bögen

    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # 1. Lila Außenkreis
    d.ellipse([m, m, S - m - 1, S - m - 1], fill=_LILA)

    # 2. Innere Statusscheibe
    d.ellipse(
        [cx - r_in, cy - r_in, cx + r_in - 1, cy + r_in - 1],
        fill=_STATUS[status],
    )

    # 3. Sync-Pfeile — zwei Bögen im Uhrzeigersinn, je ~105°
    #    Winkel-Konvention Pillow: 0°=rechts, 90°=unten, steigt UZS
    #    Bogen 1: 50°→155° (rechts-unten → links, unter dem Zentrum)
    #    Bogen 2: 230°→335° (links-oben → rechts, über dem Zentrum)
    sw = max(S // 28, 2)
    arc_bbox = [cx - r_arr, cy - r_arr, cx + r_arr, cy + r_arr]
    d.arc(arc_bbox, start=50,  end=155, fill=_WHITE, width=sw)
    d.arc(arc_bbox, start=230, end=335, fill=_WHITE, width=sw)

    # Pfeilspitzen am Ende jedes Bogens (Tangentialrichtung UZS)
    ah  = sw * 2.4   # Länge der Pfeilspitze
    hw  = sw * 1.15  # Halbe Basisbreite

    def _arrowhead(theta_deg: float) -> None:
        t  = math.radians(theta_deg)
        px = cx + r_arr * math.cos(t)
        py = cy + r_arr * math.sin(t)
        tx, ty = -math.sin(t), math.cos(t)   # Tangente UZS
        nx, ny = -ty, tx                       # Normale (links der Tangente)
        tip   = (px + tx * ah * 0.55,  py + ty * ah * 0.55)
        base1 = (px - tx * ah * 0.45 + nx * hw, py - ty * ah * 0.45 + ny * hw)
        base2 = (px - tx * ah * 0.45 - nx * hw, py - ty * ah * 0.45 - ny * hw)
        d.polygon([tip, base1, base2], fill=_WHITE)

    _arrowhead(155)
    _arrowhead(335)

    # 4. EKG-Puls-Zacken auf der Innenscheibe
    lw  = max(S // 48, 2)
    h   = r_in * 0.52   # Spike-Höhe
    pts = [
        (cx - r_in * 0.72, cy),
        (cx - r_in * 0.22, cy),
        (cx - r_in * 0.03, cy - h),
        (cx + r_in * 0.13, cy + h * 0.45),
        (cx + r_in * 0.28, cy),
        (cx + r_in * 0.72, cy),
    ]
    for i in range(len(pts) - 1):
        d.line([pts[i], pts[i + 1]], fill=_WHITE, width=lw)

    return img.resize((size, size), Image.LANCZOS)


# ------------------------------------------------------------------
# Öffentliche API — Rückgabe von 64×64-Tray-Icons
# ------------------------------------------------------------------

def icon_idle()    -> Image.Image: return _render("idle",    64)
def icon_ok()      -> Image.Image: return _render("ok",      64)
def icon_syncing() -> Image.Image: return _render("syncing", 64)
def icon_error()   -> Image.Image: return _render("error",   64)


# ------------------------------------------------------------------
# ICO-Erzeugung (16/32/48/256 px, OK-Variante als Standard)
# ------------------------------------------------------------------

_ICO_PATH = Path(__file__).parent.parent / "assets" / "garmin-sync.ico"


def generate_ico(path: str | Path = _ICO_PATH) -> None:
    """Baut garmin-sync.ico mit 16/32/48/256 px aus der OK-Variante."""
    sizes = [256, 48, 32, 16]
    images = [_render("ok", s) for s in sizes]
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    images[0].save(str(out), format="ICO", append_images=images[1:])
    print(f"Gespeichert: {out}  ({out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    generate_ico()
