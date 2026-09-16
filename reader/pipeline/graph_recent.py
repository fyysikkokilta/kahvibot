"""The /graph picture: the last few hours, one panel per machine.

Hand-drawn with Pillow, for the reason GRAPHS.md gives: a cold matplotlib import
costs 3-6 s off this Pi's SD card and the whole interaction budget is about 3 s.
Pillow is already resident because the bot composites watermarks with it.

What it shows, and why each piece earns its place:

* **The last 3 hours, not the whole day.** Nobody asks how much coffee there was
  at breakfast. A short window also spends its pixels where the answer is.
* **A grey band**, the filter's 5th-95th percentile. The old graph drew a line
  and silently omitted every reading the confidence gate rejected, which was
  about 70 % of them. Drawing the uncertainty instead means nothing is hidden:
  a diffuse frame widens the band rather than leaving a hole.
* **A dashed red temperature** on its own axis, thinner than the level so it
  never competes. Inferred from a heat balance, never measured.
* **A log power strip** under each pot. Standby at 0.5 W, hotplate at 57-182 W
  and element at ~1450 W only fit on one axis if it is logarithmic.
* **Green shading while the element draws**, which is the only time coffee can
  appear, and **a red dashed line at now** with a little space after it, so the
  series reads as ending at a moment rather than at the frame edge.

No prose anywhere: the numbers people want are burned into the photo (banner.py).
"""
from __future__ import annotations

import io
import math
import os
from datetime import datetime, timedelta

from PIL import Image, ImageDraw, ImageFont

W, H = 1000, 800
BG = (251, 250, 248)
FRAME = (201, 196, 188)
GRID = (227, 224, 218)
BODY = (43, 43, 43)
BAND = (185, 179, 171)
TEMP = (168, 50, 45)
BREW = (44, 160, 44)
NOW = (214, 39, 40)
COL = {"left": (31, 119, 180), "right": (224, 123, 0)}

FULL_ML = 1250.0
WINDOW_S = 3 * 3600.0
PAD_S = 12 * 60.0                 # breathing room to the right of "now"
BREW_W = 800.0                    # element ~1450 W, hotplate <= 182 W (measured)

PLOT_X0, PLOT_X1 = 105, 830       # right of the plot is the temperature axis
TOP, BOTTOM = 20, 745
GAP = 20
_UNITS = 3.2 + 0.95 + 3.2 + 0.95
_UNIT_PX = (BOTTOM - TOP - 3 * GAP) / _UNITS
LEVEL_H = int(3.2 * _UNIT_PX)
POWER_H = int(0.95 * _UNIT_PX)

FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
)


def _font(size, font_dir=None):
    cands = []
    if font_dir:
        cands.append(os.path.join(font_dir, "DejaVuSans-Bold.ttf"))
    cands.extend(FONT_CANDIDATES)
    for c in cands:
        if c and os.path.exists(c):
            try:
                return ImageFont.truetype(c, size)
            except OSError:
                continue
    return ImageFont.load_default()


def _panels():
    """(level_top, power_top) for each pot, top to bottom."""
    y = TOP
    out = []
    for _ in range(2):
        out.append((y, y + LEVEL_H + GAP))
        y += LEVEL_H + GAP + POWER_H + GAP
    return out


def _x_of(t, t0, t1):
    span = max(t1 - t0, 1.0)
    return PLOT_X0 + (t - t0) / span * (PLOT_X1 - PLOT_X0)


def _spans_above(power, threshold=BREW_W):
    """(start, end) wall-second pairs where the element was drawing.

    Samples arrive on change, so a value holds until the next one. A run still
    open at the end of the data is left open: the machine may still be brewing.
    """
    spans, start = [], None
    for t, w in power:
        if start is None and w >= threshold:
            start = t
        elif start is not None and w < threshold:
            spans.append((start, t))
            start = None
    if start is not None and power:
        spans.append((start, power[-1][0]))
    return spans


def _draw_level(d, top, side, series, power, t0, t1, fonts):
    x0, x1 = PLOT_X0, PLOT_X1
    y0, y1 = top, top + LEVEL_H
    d.rectangle([x0, y0, x1, y1], fill=(255, 255, 255), outline=FRAME, width=1)

    def y_of(ml):
        return y1 - min(max(ml, 0.0), 1300.0) / 1300.0 * (y1 - y0)

    for a, b in _spans_above(power):
        d.rectangle([_x_of(a, t0, t1), y0 + 1, max(_x_of(b, t0, t1), _x_of(a, t0, t1) + 2), y1 - 1],
                    fill=(226, 242, 226))
    for ml in (0, 250, 500, 750, 1000, 1250):
        y = y_of(ml)
        d.line([x0 + 1, y, x1 - 1, y], fill=GRID)
        label = str(ml)
        w = d.textlength(label, font=fonts["tick"])
        d.text((x0 - 12 - w, y - 12), label, font=fonts["tick"], fill=BODY)
    d.text((14, (y0 + y1) // 2 - 12), "ml", font=fonts["axis"], fill=BODY)

    # temperature first, so the level draws over it where they cross
    pts = [(_x_of(t, t0, t1), y1 - min(max(c, 0.0), 100.0) / 100.0 * (y1 - y0))
           for t, c in series["temp"]]
    _dashed(d, pts, TEMP, width=3, dash=14, gap=9)
    for c in (20, 60, 100):
        y = y1 - c / 100.0 * (y1 - y0)
        d.text((x1 + 12, y - 12), str(c), font=fonts["tick"], fill=TEMP)
    d.text((x1 + 12, y0 + 30), "\u00b0C", font=fonts["axis"], fill=TEMP)

    band = series["band"]
    if len(band) > 1:
        poly = [(_x_of(t, t0, t1), y_of(hi)) for t, _lo, hi in band]
        poly += [(_x_of(t, t0, t1), y_of(lo)) for t, lo, _hi in reversed(band)]
        d.polygon(poly, fill=BAND)

    line = [(_x_of(t, t0, t1), y_of(ml)) for t, ml in series["level"]]
    if len(line) > 1:
        d.line(line, fill=COL[side], width=5, joint="curve")


def _draw_power(d, top, power, t0, t1, fonts):
    x0, x1 = PLOT_X0, PLOT_X1
    y0, y1 = top, top + POWER_H
    d.rectangle([x0, y0, x1, y1], fill=(255, 255, 255), outline=FRAME, width=1)

    def y_of(w):
        w = min(max(w, 1.0), 3000.0)
        return y1 - (math.log10(w) / math.log10(3000.0)) * (y1 - y0)

    for a, b in _spans_above(power):
        d.rectangle([_x_of(a, t0, t1), y0 + 1, max(_x_of(b, t0, t1), _x_of(a, t0, t1) + 2), y1 - 1],
                    fill=(226, 242, 226))
    for w, label in ((100.0, "100 W"), (1000.0, "1 kW")):
        y = y_of(w)
        d.line([x0 + 1, y, x1 - 1, y], fill=GRID)
        tw = d.textlength(label, font=fonts["small"])
        d.text((x0 - 10 - tw, y - 10), label, font=fonts["small"], fill=BODY)
    _dashed(d, [(x0 + 1, y_of(BREW_W)), (x1 - 1, y_of(BREW_W))], BREW, width=1, dash=4, gap=5)

    pts = []
    for i, (t, w) in enumerate(power):
        x = _x_of(t, t0, t1)
        if i:
            pts.append((x, pts[-1][1]))         # hold until the next report
        pts.append((x, y_of(w)))
    if power:
        pts.append((_x_of(min(t1, power[-1][0] + 600.0), t0, t1), pts[-1][1]))
    if len(pts) > 1:
        d.line(pts, fill=BODY, width=3)


def _dashed(d, pts, colour, width=2, dash=10, gap=6):
    """Pillow has no dash pattern; walk the polyline and stroke alternate runs.

    `carry` converges on `dash` across a long polyline of short segments, and
    once `dash - carry` falls below the ULP of `pos`, `pos + step` rounds back
    to `pos`: the walk stops advancing, `end - pos` stays 0 so the run never
    toggles, `carry` never grows, and the loop spins forever. Not hypothetical
    -- it wedged the reader for 21 h on 2026-09-15 on the temperature line,
    where a 10 s cadence over a near-constant temp_c produces exactly that
    geometry (carry 13.999999999999998 against dash 14, step half an ULP).

    So a run too small to move `pos` counts as finished rather than retried,
    and `stalls` bounds the degenerate case where even a full fresh run cannot
    advance. Every iteration now either moves `pos` or runs the counter down.
    """
    carry, on = 0.0, True
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        seg = math.hypot(x2 - x1, y2 - y1)
        if not seg > 0:                     # > 0 rather than <= 0, to skip NaN
            continue
        pos, stalls = 0.0, 0
        while pos < seg:
            step = (dash if on else gap) - carry
            end = min(pos + step, seg) if step > 0 else pos
            if end <= pos:
                on, carry = not on, 0.0     # this run is spent; start the next
                stalls += 1
                if stalls > 2:
                    break                   # dash and gap are both unusable
                continue
            stalls = 0
            if on:
                d.line([x1 + (x2 - x1) * pos / seg, y1 + (y2 - y1) * pos / seg,
                        x1 + (x2 - x1) * end / seg, y1 + (y2 - y1) * end / seg],
                       fill=colour, width=width)
            if end - pos >= step:
                on, carry = not on, 0.0
            else:
                carry += end - pos
            pos = end


def _series_for(records, side, t0):
    """level, band and temperature points for one pot, oldest first."""
    level, band, temp = [], [], []
    for r in records:
        t = r["_wall"]
        if t < t0:
            continue
        pot = next((p for p in r["pots"] if p.get("side") == side), None)
        if pot is None:
            continue
        ml = pot.get("f_ml")
        if ml is None:
            ml = pot.get("volume_ml")
        if ml is not None:
            level.append((t, float(ml)))
        lo, hi = pot.get("f_lo"), pot.get("f_hi")
        if lo is not None and hi is not None:
            band.append((t, float(lo), float(hi)))
        c = pot.get("temp_c")
        if c is not None:
            temp.append((t, float(c)))
    return {"level": level, "band": band, "temp": temp}


def render(records, power_history, now_wall, window_s=WINDOW_S, font_dir=None):
    """PNG bytes for the last `window_s` seconds, or None if there is nothing yet.

    `records` are the day buffer's, each with `_wall` and pots carrying at least
    volume_ml and ideally the filter's f_ml/f_lo/f_hi/temp_c.
    `power_history` is {side: [(wall_seconds, watts), ...]}.
    """
    t1 = now_wall
    t0 = t1 - window_s
    t_right = t1 + PAD_S
    series = {s: _series_for(records, s, t0) for s in ("left", "right")}
    if not any(series[s]["level"] for s in series):
        return None

    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    fonts = {"tick": _font(22, font_dir), "axis": _font(19, font_dir),
             "small": _font(15, font_dir)}

    for (level_top, power_top), side in zip(_panels(), ("left", "right")):
        power = [(t, w) for t, w in (power_history or {}).get(side, []) if t >= t0]
        _draw_level(d, level_top, side, series[side], power, t0, t_right, fonts)
        _draw_power(d, power_top, power, t0, t_right, fonts)

    # time axis, labelled once at the bottom
    tick = datetime.fromtimestamp(t0).replace(second=0, microsecond=0)
    tick += timedelta(minutes=(30 - tick.minute % 30) % 30)
    while tick.timestamp() <= t_right:
        x = _x_of(tick.timestamp(), t0, t_right)
        if PLOT_X0 <= x <= PLOT_X1:
            label = tick.strftime("%H:%M")
            tw = d.textlength(label, font=fonts["tick"])
            d.text((x - tw / 2, BOTTOM + 6), label, font=fonts["tick"], fill=BODY)
            for top, _p in _panels():
                d.line([x, top, x, top + LEVEL_H], fill=GRID)
        tick += timedelta(minutes=30)

    # now, on every panel
    x_now = _x_of(t1, t0, t_right)
    for level_top, power_top in _panels():
        _dashed(d, [(x_now, level_top), (x_now, level_top + LEVEL_H)], NOW, width=3, dash=10, gap=8)
        _dashed(d, [(x_now, power_top), (x_now, power_top + POWER_H)], NOW, width=3, dash=10, gap=8)

    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()
