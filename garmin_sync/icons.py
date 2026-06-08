"""
Tray-Icons und App-Icon für garmin-sync.

Zwei Render-Varianten:
  _render_small  — vereinfacht (kein Sync-Pfeil), kräftiger Puls → für Tray (64 px)
  _render_full   — mit Sync-Pfeilen → für .ico / große Darstellungen

Anti-Aliasing via 4×-Supersampeln (Pillow, LANCZOS-Downscale).

ICO regenerieren:
    .venv\\Scripts\\python garmin_sync/icons.py
PNG-Previews:
    .venv\\Scripts\\python -c "from garmin_sync.icons import generate_previews; generate_previews()"
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw

_LILA  = (0x7C, 0x4D, 0xCA, 255)
_WHITE = (255, 255, 255, 255)
_STATUS: dict[str, tuple[int, int, int, int]] = {
    "idle":    (0x88, 0x93, 0xA5, 255),  # grau
    "ok":      (0x0A, 0x8A, 0x5F, 255),  # grün
    "syncing": (0xE8, 0x92, 0x3C, 255),  # orange
    "error":   (0xD6, 0x45, 0x45, 255),  # rot
}

_SUPER = 4  # Supersample-Faktor


def _render_small(status: str, size: int) -> Image.Image:
    """
    Tray-Variante: lila Ring + große Statusscheibe + kräftiger Puls.
    Keine Sync-Pfeile — bleibt bei 16 px klar erkennbar.
    Strichstärke >= 8 % der Bildbreite.
    """
    S  = size * _SUPER
    cx = cy = S // 2

    m     = max(S // 20, 1)
    r_out = S // 2 - m
    r_in  = int(r_out * 0.64)   # große Innenscheibe (64 % des Außenradius)

    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d   = ImageDraw.Draw(img)

    # Lila Außenkreis
    d.ellipse([m, m, S - m - 1, S - m - 1], fill=_LILA)

    # Innere Statusscheibe
    d.ellipse(
        [cx - r_in, cy - r_in, cx + r_in - 1, cy + r_in - 1],
        fill=_STATUS[status],
    )

    # Kräftiger EKG-Puls (>= 8 % der Ausgabe-Breite)
    lw  = max(S // 12, 3)      # ~21 px bei S=256 → ~5 px bei 64px = 8 %
    h   = r_in * 0.50
    pts = [
        (cx - r_in * 0.72, cy),
        (cx - r_in * 0.20, cy),
        (cx - r_in * 0.03, cy - h),
        (cx + r_in * 0.13, cy + h * 0.45),
        (cx + r_in * 0.27, cy),
        (cx + r_in * 0.72, cy),
    ]
    for i in range(len(pts) - 1):
        d.line([pts[i], pts[i + 1]], fill=_WHITE, width=lw)

    return img.resize((size, size), Image.LANCZOS)


def _render_full(status: str, size: int) -> Image.Image:
    """
    Detaillierte Variante mit Sync-Pfeilen — für .ico und große Darstellungen.
    """
    S  = size * _SUPER
    cx = cy = S // 2

    m     = max(S // 16, 1)
    r_out = S // 2 - m
    r_in  = r_out // 2
    r_arr = (r_out + r_in + 1) // 2

    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d   = ImageDraw.Draw(img)

    # Lila Außenkreis
    d.ellipse([m, m, S - m - 1, S - m - 1], fill=_LILA)

    # Innere Statusscheibe
    d.ellipse(
        [cx - r_in, cy - r_in, cx + r_in - 1, cy + r_in - 1],
        fill=_STATUS[status],
    )

    # Sync-Pfeile: zwei UZS-Bögen (50°→155°, 230°→335°) + Pfeilspitzen
    # Winkel-Konvention Pillow: 0°=rechts, 90°=unten, steigt UZS
    sw       = max(S // 28, 2)
    arc_bbox = [cx - r_arr, cy - r_arr, cx + r_arr, cy + r_arr]
    d.arc(arc_bbox, start=50,  end=155, fill=_WHITE, width=sw)
    d.arc(arc_bbox, start=230, end=335, fill=_WHITE, width=sw)

    ah = sw * 2.4
    hw = sw * 1.15

    def _arrowhead(theta_deg: float) -> None:
        t       = math.radians(theta_deg)
        px      = cx + r_arr * math.cos(t)
        py      = cy + r_arr * math.sin(t)
        tx, ty  = -math.sin(t), math.cos(t)   # Tangente UZS
        nx, ny  = -ty, tx                       # Normale
        tip     = (px + tx * ah * 0.55,  py + ty * ah * 0.55)
        base1   = (px - tx * ah * 0.45 + nx * hw, py - ty * ah * 0.45 + ny * hw)
        base2   = (px - tx * ah * 0.45 - nx * hw, py - ty * ah * 0.45 - ny * hw)
        d.polygon([tip, base1, base2], fill=_WHITE)

    _arrowhead(155)
    _arrowhead(335)

    # EKG-Puls-Zacken
    lw  = max(S // 48, 2)
    h   = r_in * 0.52
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
# Öffentliche API — 64×64-Tray-Icons (simplified, ohne Pfeile)
# Windows skaliert 64 px sauber auf 16–24 px herunter.
# ------------------------------------------------------------------

def icon_idle()    -> Image.Image: return _render_small("idle",    64)
def icon_ok()      -> Image.Image: return _render_small("ok",      64)
def icon_syncing() -> Image.Image: return _render_small("syncing", 64)
def icon_error()   -> Image.Image: return _render_small("error",   64)


# ------------------------------------------------------------------
# ICO-Erzeugung (16/32/48/256 px, full design mit Pfeilen)
# ------------------------------------------------------------------

_ICO_PATH = Path(__file__).parent.parent / "assets" / "garmin-sync.ico"


def generate_ico(path: str | Path = _ICO_PATH) -> None:
    """Baut garmin-sync.ico mit 16/32/48/256 px (full design, OK-Variante)."""
    sizes  = [256, 48, 32, 16]
    images = [_render_full("ok", s) for s in sizes]
    out    = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    images[0].save(str(out), format="ICO", append_images=images[1:])
    print(f"Gespeichert: {out}  ({out.stat().st_size // 1024} KB)")


# ------------------------------------------------------------------
# PNG-Previews für Reviewer
# ------------------------------------------------------------------

_PREVIEW_PATH = Path(__file__).parent.parent / "_privat" / "icon_preview"


def generate_previews(path: str | Path = _PREVIEW_PATH) -> None:
    """Rendert PNG-Previews für Reviewer: small+full, je 64 px und 16 px."""
    out = Path(path)
    out.mkdir(parents=True, exist_ok=True)
    _render_small("ok", 64).save(str(out / "tray_small_64px.png"))
    _render_small("ok", 16).save(str(out / "tray_small_16px.png"))
    _render_full("ok",  64).save(str(out / "ico_full_64px.png"))
    _render_full("ok", 256).save(str(out / "ico_full_256px.png"))
    print(f"Previews gespeichert in: {out}")
    for p in sorted(out.glob("*.png")):
        print(f"  {p.name}")


if __name__ == "__main__":
    generate_ico()
    generate_previews()
