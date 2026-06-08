"""
Tray-Icons und App-Icon für garmin-sync.

Zwei Render-Varianten:
  _render_small  — ohne Sync-Pfeil, für Tray; exakt in nativer DPI-Größe
  _render_full   — mit Sync-Pfeilen, für .ico / große Darstellungen

Anti-Aliasing via 4×-Supersampeln (Pillow, LANCZOS-Downscale).
Tray-Größe: DPI-nativ per GetSystemMetrics(SM_CXSMICON), Fallback 32 px.

ICO regenerieren:
    .venv\\Scripts\\python garmin_sync/icons.py
PNG-Previews (16/20/24/32 px für Reviewer):
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


def _get_tray_size() -> int:
    """
    Native Small-Icon-Größe des aktuellen Monitors.
    SM_CXSMICON (49) liefert 16/20/24/32 px je nach DPI-Skalierung.
    Tray-Icon wird exakt in dieser Größe gerendert — kein Windows-Downscale.
    """
    try:
        import ctypes
        SM_CXSMICON = 49
        size = ctypes.windll.user32.GetSystemMetrics(SM_CXSMICON)
        if 12 <= size <= 64:
            return size
    except Exception:
        pass
    return 32  # sicherer Fallback


def _render_small(status: str, size: int) -> Image.Image:
    """
    Tray-Variante: lila Ring + große Statusscheibe + 3-Punkt-Puls.
    Keine Sync-Pfeile. Optimiert für native Pixelschärfe bei 16–32 px.

    Fix A: bei nativer Zielgröße kein Windows-Downscale nötig.
    Fix B: Margin ≈3 %, Strichstärke S//8 (≥2 px output), einfacher Zacken.
    """
    S  = size * _SUPER
    cx = cy = S // 2

    m     = max(S // 32, 1)       # ≈3 % Rand → füllt fast die ganze Fläche
    r_out = S // 2 - m
    r_in  = int(r_out * 0.64)     # große Innenscheibe (64 % des Außenradius)

    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d   = ImageDraw.Draw(img)

    # Lila Außenkreis
    d.ellipse([m, m, S - m - 1, S - m - 1], fill=_LILA)

    # Innere Statusscheibe
    d.ellipse(
        [cx - r_in, cy - r_in, cx + r_in - 1, cy + r_in - 1],
        fill=_STATUS[status],
    )

    # 3-Punkt-Puls-Zacken: links-flach → Spitze oben → rechts-flach
    # Strich S//8 → 2 px bei 16px, 3 px bei 24px, 4 px bei 32px output
    lw  = max(S // 8, 3)
    h   = r_in * 0.54
    pts = [
        (cx - r_in * 0.65, cy),   # links
        (cx,               cy - h),  # Spitze
        (cx + r_in * 0.65, cy),   # rechts
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
        tx, ty  = -math.sin(t), math.cos(t)
        nx, ny  = -ty, tx
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
# Öffentliche API — DPI-native Tray-Icons (simplified, ohne Pfeile)
# ------------------------------------------------------------------

def icon_idle()    -> Image.Image: return _render_small("idle",    _get_tray_size())
def icon_ok()      -> Image.Image: return _render_small("ok",      _get_tray_size())
def icon_syncing() -> Image.Image: return _render_small("syncing", _get_tray_size())
def icon_error()   -> Image.Image: return _render_small("error",   _get_tray_size())


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
# PNG-Previews für Reviewer (16/20/24/32 px, ok + syncing)
# ------------------------------------------------------------------

_PREVIEW_PATH = Path(__file__).parent.parent / "_privat" / "icon_preview"


def generate_previews(path: str | Path = _PREVIEW_PATH) -> None:
    """16/20/24/32 px Tray-Previews für ok + syncing; außerdem full-Design."""
    out = Path(path)
    out.mkdir(parents=True, exist_ok=True)
    for status in ("ok", "syncing"):
        for size in (16, 20, 24, 32):
            _render_small(status, size).save(str(out / f"tray_{status}_{size}px.png"))
    _render_full("ok",  64).save(str(out / "ico_full_64px.png"))
    _render_full("ok", 256).save(str(out / "ico_full_256px.png"))
    print(f"Previews gespeichert in: {out}")
    for p in sorted(out.glob("*.png")):
        print(f"  {p.name}")


if __name__ == "__main__":
    generate_ico()
    generate_previews()
