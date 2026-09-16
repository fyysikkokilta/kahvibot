"""Burn each machine's reading into the corner of the photo.

Why on the picture rather than in a caption: the number then travels with the
image when somebody forwards it, needs no second glance, and sits over the
machine it describes, which removes the left/right question that has already
caused one wrong mapping. Captions are off during burn-in anyway.

Two plates in the bottom corners, one per pot, each carrying the machine name,
the amount and - when the reader service supplies it - the temperature. Pillow
only: the bot already composites watermarks this way, so nothing new is loaded.

Failure discipline is the rest of the bot's: any problem returns the original
image untouched, because the photo is the product and a missing number must
never cost it.
"""
from __future__ import annotations

import os

from PIL import Image, ImageDraw, ImageFont

# camera side -> what people call that machine
NAMES = {"left": "EAST", "right": "WEST"}

PLATE = (15, 15, 18, 170)
WHITE = (255, 255, 255)
TEMP = (232, 106, 98)
SIDE_COLOUR = {"left": (54, 132, 191), "right": (224, 123, 0)}
UNKNOWN = "?"

_FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
)


def _font(size: int, font_path: str | None = None):
    for cand in ([font_path] if font_path else []) + list(_FONT_CANDIDATES):
        if cand and os.path.exists(cand):
            try:
                return ImageFont.truetype(cand, size)
            except OSError:
                continue
    return ImageFont.load_default()


def _pot_text(pot: dict) -> tuple:
    """(amount, temperature) as they should read, or None where unknown.

    A pot the reader could not measure shows "? ml" rather than nothing: a blank
    corner looks like a broken overlay, while a question mark is the honest
    statement that this machine was not readable in this frame.
    """
    ml = pot.get("volume_ml")
    amount = f"{ml:.0f} ml" if isinstance(ml, (int, float)) else f"{UNKNOWN} ml"
    t = pot.get("temp_c")
    temp = f"{t:.0f}\u00b0C" if isinstance(t, (int, float)) else None
    return amount, temp


def draw(img: "Image.Image", reading: dict | None, names: dict | None = None,
         font_path: str | None = None, pad: int = 16, scale: float = 1.0):
    """Return a copy of `img` with a reading plate in each bottom corner."""
    if not reading:
        return img
    pots = {p.get("side"): p for p in (reading.get("pots") or []) if p.get("side")}
    if not pots:
        return img
    names = names or NAMES

    W, H = img.size
    s = scale * W / 1280.0                      # keep proportions if the camera changes
    f_name = _font(max(int(24 * s), 10), font_path)
    f_amount = _font(max(int(58 * s), 16), font_path)
    f_temp = _font(max(int(32 * s), 12), font_path)
    pad = int(pad * s)

    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    blocks = []
    for side in ("left", "right"):
        pot = pots.get(side)
        if pot is None:
            continue
        amount, temp = _pot_text(pot)
        label = names.get(side, side.upper())
        lines = [(label, f_name), (amount, f_amount)] + ([(temp, f_temp)] if temp else [])
        width = max(d.textlength(t, font=f) for t, f in lines) + int(34 * s)
        height = int((12 + 28 + 68 + (40 if temp else 0)) * s)
        x0 = pad if side == "left" else W - pad - width
        y0 = H - pad - height
        d.rounded_rectangle([x0, y0, x0 + width, y0 + height],
                            radius=max(int(16 * s), 4), fill=PLATE)
        blocks.append((side, x0 + int(17 * s), y0 + int(10 * s), amount, temp, label))

    out = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    d = ImageDraw.Draw(out)
    for side, x, y, amount, temp, label in blocks:
        d.text((x, y), label, font=f_name, fill=SIDE_COLOUR.get(side, WHITE))
        d.text((x, y + int(28 * s)), amount, font=f_amount, fill=WHITE)
        if temp:
            d.text((x, y + int(96 * s)), temp, font=f_temp, fill=TEMP)
    return out


def safe_draw(img, reading, logger=None, **kw):
    """draw(), but never raises: the photo goes out with or without the overlay."""
    try:
        return draw(img, reading, **kw)
    except Exception:
        if logger is not None:
            logger.warning("photo banner failed", exc_info=True)
        return img
