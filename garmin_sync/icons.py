from PIL import Image, ImageDraw

_SIZE = 64


def _circle(color: str) -> Image.Image:
    img = Image.new("RGBA", (_SIZE, _SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    m = 4
    d.ellipse([m, m, _SIZE - m, _SIZE - m], fill=color)
    return img


def icon_ok() -> Image.Image:
    return _circle("#27ae60")  # green — synced OK


def icon_error() -> Image.Image:
    return _circle("#e74c3c")  # red — error / not logged in


def icon_syncing() -> Image.Image:
    return _circle("#f39c12")  # orange — sync in progress


def icon_idle() -> Image.Image:
    return _circle("#7f8c8d")  # gray — running, no sync yet today
