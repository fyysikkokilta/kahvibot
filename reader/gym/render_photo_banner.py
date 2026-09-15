"""Overlay the reading on the photo itself: each machine's amount and temperature
in the corner above it.

Worth trying because captions are off. A number burned into the picture travels
with it when someone forwards the photo, needs no second glance at a caption,
and sits directly over the machine it describes, which removes the left/right
question entirely.

Drawn with Pillow, which is what kahvibot already uses to composite watermarks,
so this ports to the bot as-is.


Paths come from the environment so this runs anywhere:
COFFEE_GRAPH_DATA (readings + power CSVs), COFFEE_GRAPH_OUT (where the
images go), and for the banner COFFEE_GRAPH_FONT.
"""
import json
import math
import os
import pathlib
import sys
from datetime import datetime, timedelta

from PIL import Image, ImageDraw, ImageFont

READER = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(READER))
import numpy as np  # noqa: E402

from pipeline.rbpf import Calibration, PotRBPF  # noqa: E402
from pipeline.reader import row_dist  # noqa: E402

S = pathlib.Path(os.environ.get("COFFEE_GRAPH_DATA", "graph_data"))
OUT = pathlib.Path(os.environ.get("COFFEE_GRAPH_OUT", "graph_proposals"))
FONT = pathlib.Path(os.environ.get("COFFEE_GRAPH_FONT", "")) if os.environ.get("COFFEE_GRAPH_FONT") else _find_font()

def _find_font():
    """A bold sans-serif, wherever this happens to run."""
    for c in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
              "C:/Windows/Fonts/arialbd.ttf"):
        if os.path.exists(c):
            return pathlib.Path(c)
    return None


COL = {"left": (54, 132, 191), "right": (224, 123, 0)}
LABEL = {"left": "EAST", "right": "WEST"}
TEMP_COL = (232, 106, 98)
WHITE = (255, 255, 255)
ROWS, Y_BASE, Y_TOP = 256, 0.88, 0.12
CAL = Calibration(READER / "models" / "calibration.json")


def sd_from_entropy(e):
    return float(np.clip(math.exp(3.62 + 6.0 * (e - 0.52)), 15.0, 400.0))


def gaussian_rowdist(h, sd_ml):
    span = Y_BASE - Y_TOP
    row = (Y_BASE - h * span) * (ROWS - 1)
    sd_rows = max(sd_ml / 1250.0 * span * (ROWS - 1), 0.8)
    g = np.arange(ROWS, dtype=float)
    logits = np.zeros((3, ROWS))
    logits[2] = -0.5 * ((g - row) / sd_rows) ** 2
    return row_dist(logits, Y_BASE, Y_TOP)


def state_at(frame_time):
    """Run the filter up to the moment the photo was taken, so the numbers on the
    picture are the numbers for that picture."""
    recs = []
    for line in (S / "gdata" / "readings_tail.jsonl").read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            r = json.loads(line)
        except Exception:
            continue
        if "pots" in r and "t" in r:
            recs.append((datetime.fromisoformat(r["t"]), r["pots"]))
    recs.sort(key=lambda x: x[0])
    power = {}
    for name, side in (("vasen", "left"), ("oikea", "right")):
        rows = []
        for line in (S / "gdata" / f"power_{name}.csv").read_text().splitlines()[1:]:
            ts, w = line.split(",")
            rows.append((datetime.fromisoformat(ts), float(w)))
        power[side] = rows

    def power_at(rows, t):
        v = None
        for ts, w in rows:
            if ts <= t:
                v = w
            else:
                break
        return v

    out = {}
    for side in ("left", "right"):
        f = PotRBPF(CAL, n_particles=1200, seed=7)
        prev, post = None, None
        for t, pots in recs:
            if t > frame_time:
                break
            q = next((p for p in pots if p["s"] == side), None)
            dt = 0.0 if prev is None else (t - prev).total_seconds()
            prev = t
            rd = gaussian_rowdist(q["h"], sd_from_entropy(q.get("e", 0.6))) \
                if q and q.get("h") is not None else None
            post = f.step(dt=min(dt, 300.0), power_w=power_at(power[side], t),
                          rowdist=rd, surface_logit=2.0)
        out[side] = post
    return out


def draw_corner(d, img, side, post, position, box_h, pad=18):
    """One corner block: label, amount, temperature."""
    W, H = img.size
    f_label = ImageFont.truetype(str(FONT), 26)
    f_big = ImageFont.truetype(str(FONT), 62)
    f_temp = ImageFont.truetype(str(FONT), 34)
    amount = f"{post.ml_median:.0f} ml"
    temp = f"{post.temp_mean:.0f}\u00b0C"
    right = side == "right"
    y0 = 0 if position == "top" else H - box_h
    x = W - pad if right else pad
    anchor_h = "r" if right else "l"
    d.text((x, y0 + 10), LABEL[side], font=f_label, fill=COL[side], anchor=anchor_h + "a")
    d.text((x, y0 + 40), amount, font=f_big, fill=WHITE, anchor=anchor_h + "a")
    d.text((x, y0 + 108), temp, font=f_temp, fill=TEMP_COL, anchor=anchor_h + "a")


def banner(img_path, position="top", height=152, opacity=165, fname="banner_top.jpg"):
    img = Image.open(img_path).convert("RGB")
    W, H = img.size
    state = STATE
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    y0 = 0 if position == "top" else H - height
    d.rectangle([0, y0, W, y0 + height], fill=(15, 15, 18, opacity))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    d = ImageDraw.Draw(img)
    for side in ("left", "right"):
        draw_corner(d, img, side, state[side], position, height)
    img.save(OUT / fname, quality=88)
    print("wrote", OUT / fname)


def corners_only(img_path, fname="banner_corners.jpg", pad=16):
    """No bar: two rounded plates, one over each machine. Hides less of the photo."""
    img = Image.open(img_path).convert("RGBA")
    W, H = img.size
    f_label = ImageFont.truetype(str(FONT), 24)
    f_big = ImageFont.truetype(str(FONT), 58)
    f_temp = ImageFont.truetype(str(FONT), 32)
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    boxes = {}
    for side in ("left", "right"):
        post = STATE[side]
        amount = f"{post.ml_median:.0f} ml"
        temp = f"{post.temp_mean:.0f}\u00b0C"
        w = max(d.textlength(LABEL[side], font=f_label),
                d.textlength(amount, font=f_big),
                d.textlength(temp, font=f_temp)) + 34
        h = 150
        x0 = pad if side == "left" else W - pad - w
        d.rounded_rectangle([x0, pad, x0 + w, pad + h], radius=16, fill=(15, 15, 18, 170))
        boxes[side] = (x0 + 17, pad + 12, amount, temp)
    img = Image.alpha_composite(img, overlay).convert("RGB")
    d = ImageDraw.Draw(img)
    for side, (tx, ty, amount, temp) in boxes.items():
        d.text((tx, ty), LABEL[side], font=f_label, fill=COL[side])
        d.text((tx, ty + 28), amount, font=f_big, fill=WHITE)
        d.text((tx, ty + 96), temp, font=f_temp, fill=TEMP_COL)
    img.save(OUT / fname, quality=88)
    print("wrote", OUT / fname)


if __name__ == "__main__":
    frame = S / "gdata" / "banner_frame.jpg"
    stamp = datetime.strptime(frame.stem if frame.stem[0].isdigit() else "20260915T131340Z",
                              "%Y%m%dT%H%M%SZ") if False else None
    # the retained filename carries the UTC instant the frame was captured
    name = "20260915T131340Z"
    ft = datetime.strptime(name, "%Y%m%dT%H%M%SZ").replace(tzinfo=None)
    from datetime import timezone
    ft = ft.replace(tzinfo=timezone.utc)
    STATE = state_at(ft)
    for side in ("left", "right"):
        p = STATE[side]
        print(f"{LABEL[side]}: {p.ml_median:.0f} ml [{p.ml_lo:.0f}, {p.ml_hi:.0f}]  {p.temp_mean:.0f} C")
    banner(frame, "top", fname="banner_top.jpg")
    banner(frame, "bottom", fname="banner_bottom.jpg")
    corners_only(frame)
