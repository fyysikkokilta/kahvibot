# -*- coding: utf-8 -*-
"""
Today's coffee level as a picture — the /graph command.

Implements GRAPHS.md (coffee10). The decisions that matter live there; the
short version that constrains this file:

  * the axis is cups, never millilitres (§2.1);
  * each pot is a translucent band whose half-width IS the 29 ml median error,
    with a 2 px centre line — the stroke width is the error bar (§2.2);
  * abstentions and missing carafes get their own rug strip, never a height
    (§2.3);
  * readings more than 25 min apart are never joined by a solid line (§2.4);
  * raw readings only — no smoothed/fitted curve (§3.1);
  * brews render as an interval band between the bracketing readings, never
    as an instant (§3.2);
  * hand-drawn Pillow, no matplotlib (§4.1); geometry fixed at 1000×640 (§6.2).

Everything here is pure: no telegram imports, no config imports. The bot calls
graph_reply() and sends whatever comes back. Any exception is the caller's to
catch and degrade to text — a broken graph must never take out /status.
"""

import io
import json
import os
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

# --- model facts (GRAPHS.md §0, §2.2) -------------------------------------
ERROR_ML = 29.0          # median error vs held-out labels; NOT the 11 ml repeatability
BREW_RISE_ML = 300.0     # smooth.find_change_points(rise_ml=...) — a rise this big is a brew
MAX_GAP_MIN = 25.0       # smooth.py max_gap_minutes: larger gaps break the line
CUP_ML = 125.0
AXIS_ML = 1250.0         # 10 cups, always — days must be comparable (§6.4)

# --- geometry (§6.2) --------------------------------------------------------
W, H = 1000, 640
PLOT = (96, 96, 976, 520)                    # x0, y0, x1, y1
PX_PER_ML = (PLOT[3] - PLOT[1]) / AXIS_ML    # 0.3392

BG = "#fbfaf8"
FRAME = "#c9c4bc"
GRID_MAJOR = "#e3e0da"
GRID_MINOR = "#efede8"
TEXT_DARK = "#1a1a1a"
TEXT_BODY = "#2b2b2b"
TEXT_DIM = "#5a5a5a"
TEXT_FOOT = "#6a6a6a"
RUG_ABSENT = "#9a948c"
COLOURS = {"left": "#1f77b4", "right": "#e07b00"}   # CVD-safe pair (§5.5)
BREW = "#2ca02c"

FI_WEEKDAYS = ["ma", "ti", "ke", "to", "pe", "la", "su"]

# single-entry render cache (§4.3)
_cache = {"key": None, "png": None, "caption": None}


# ---------------------------------------------------------------------------
# data plumbing (§7)
# ---------------------------------------------------------------------------

def _parse_ts(s):
    # records are UTC ISO-8601; tolerate a trailing Z
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, TypeError, AttributeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _record_time(rec):
    # §7.1: captured_at, falling back to read_at. Never the file stem.
    return _parse_ts(rec.get("captured_at")) or _parse_ts(rec.get("read_at"))


def _tail_lines(path, cutoff_utc, chunk=256 * 1024, max_bytes=32 * 1024 * 1024):
    """Read whole lines from the end of the log until the first full line is
    older than cutoff_utc (or the file/byte budget is exhausted).

    GRAPHS.md §7.3 sizes the tail at 256 KB for user-driven photos; the 10 s
    sampler makes the same file ~40x denser, so the tail grows in 256 KB steps
    instead of being fixed — bounded work either way."""
    with open(path, "rb") as fh:
        fh.seek(0, os.SEEK_END)
        size = fh.tell()
        take = min(chunk, size)
        while True:
            fh.seek(size - take)
            blob = fh.read(take)
            lines = blob.split(b"\n")
            # first element may be a partial line unless we read the whole file
            head = 1 if take < size else 0
            first_full = None
            for ln in lines[head:]:
                if ln.strip():
                    first_full = ln
                    break
            if take >= size or take >= max_bytes:
                break
            if first_full is not None:
                try:
                    t = _record_time(json.loads(first_full))
                except (ValueError, UnicodeDecodeError):
                    t = None
                if t is not None and t < cutoff_utc:
                    break
            take = min(size, max_bytes, take + chunk)
        out = []
        for ln in lines[head:]:
            ln = ln.strip()
            if ln:
                try:
                    out.append(ln.decode("utf-8"))
                except UnicodeDecodeError:
                    pass
        return out


def load_today(log_pattern, now_utc):
    """Parse today's (local calendar day, §7.4) records from the current log
    file. Returns a list of dicts each with '_t' (aware UTC datetime) added,
    sorted by time. Unparseable lines are skipped; records without pots are
    kept (they are failed captures and count as photos, §7.2)."""
    now_local = now_utc.astimezone()
    # the bot expands the pattern with LOCAL now at write time; a today-record
    # was by definition written today local, so one file holds them all
    path = now_local.strftime(log_pattern)
    if not os.path.isfile(path):
        return []
    day_start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    cutoff_utc = day_start_local.astimezone(timezone.utc)
    records = []
    for line in _tail_lines(path, cutoff_utc):
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if not isinstance(rec, dict):
            continue
        t = _record_time(rec)
        if t is None:
            continue
        if t.astimezone().date() != now_local.date():
            continue
        rec["_t"] = t
        records.append(rec)
    records.sort(key=lambda r: r["_t"])
    return records


class DaySeries(object):
    """Everything the renderer and the caption need, precomputed."""

    def __init__(self, records, now_utc):
        self.now_utc = now_utc
        self.n_photos = len(records)
        self.n_readable = 0
        self.usable = {"left": [], "right": []}   # (t_utc, ml)
        self.rug = {"left": [], "right": []}      # (t_utc, "abstain"|"absent")
        for rec in records:
            pots = rec.get("pots")
            if not isinstance(pots, list):
                continue   # error record: a photo, but not an observation of a side
            by_side = {}
            for p in pots:
                if isinstance(p, dict) and p.get("side") in ("left", "right"):
                    by_side[p["side"]] = p
            any_ok = False
            for side in ("left", "right"):
                p = by_side.get(side)
                if p is None:
                    self.rug[side].append((rec["_t"], "absent"))
                elif p.get("ok") and isinstance(p.get("volume_ml"), (int, float)):
                    # §7.1: never trust volume_ml unless ok is true
                    self.usable[side].append((rec["_t"], float(p["volume_ml"])))
                    any_ok = True
                else:
                    self.rug[side].append((rec["_t"], "abstain"))
            if any_ok:
                self.n_readable += 1
        for side in ("left", "right"):
            self.usable[side].sort(key=lambda x: x[0])
            self.rug[side].sort(key=lambda x: x[0])
        self.brews = {s: self._find_brews(self.usable[s]) for s in ("left", "right")}

    @staticmethod
    def _find_brews(readings):
        """(t_before, t_after) pairs where the level rose >= BREW_RISE_ML —
        the rise-only rule of smooth.find_change_points (§3.2)."""
        out = []
        for (t0, ml0), (t1, ml1) in zip(readings, readings[1:]):
            if ml1 - ml0 >= BREW_RISE_ML:
                out.append((t0, t1))
        return out

    def segments(self, side):
        """Usable readings split wherever the gap exceeds MAX_GAP_MIN (§2.4)."""
        segs, cur = [], []
        for t, ml in self.usable[side]:
            if cur and (t - cur[-1][0]).total_seconds() / 60.0 > MAX_GAP_MIN:
                segs.append(cur)
                cur = []
            cur.append((t, ml))
        if cur:
            segs.append(cur)
        return segs

    def enough_for_graph(self):
        """§3.3: >= 3 usable readings AND span >= 60 min, on either pot."""
        for side in ("left", "right"):
            u = self.usable[side]
            if len(u) >= 3 and (u[-1][0] - u[0][0]) >= timedelta(minutes=60):
                return True
        return False

    def all_event_times(self):
        ts = [t for s in ("left", "right") for t, _ in self.usable[s]]
        ts += [t for s in ("left", "right") for t, _ in self.rug[s]]
        return ts

    def latest_reading_time(self):
        ts = [u[-1][0] for u in self.usable.values() if u]
        return max(ts) if ts else None

    def latest_brew(self):
        pairs = [b for side in ("left", "right") for b in self.brews[side]]
        return max(pairs, key=lambda b: b[1]) if pairs else None


# ---------------------------------------------------------------------------
# text: captions and fallbacks (§5.2, §5.3)
# ---------------------------------------------------------------------------

def _half_cup_phrase(ml, fi):
    hc = round(ml / (CUP_ML / 2.0)) / 2.0
    if hc <= 0:
        return "tyhjä" if fi else "empty"
    whole = int(hc)
    s = (str(whole) if whole else "") + ("½" if hc != whole else "")
    if hc == 1.0:
        return "~1 kuppi" if fi else "~1 cup"
    return ("~%s kuppia" % s) if fi else ("~%s cups" % s)


def _hhmm(t_utc):
    return t_utc.astimezone().strftime("%H:%M")


def _ago(delta):
    mins = int(delta.total_seconds() // 60)
    h, m = divmod(max(mins, 0), 60)
    if h and m:
        return "%d h %d min" % (h, m)
    if h:
        return "%d h" % h
    return "%d min" % m


def _brew_phrase(day, fi):
    brew = day.latest_brew()
    if brew is None:
        return "ei havaittua keittoa tänään" if fi else "no brew detected today"
    t0, t1 = brew
    if (t1 - t0) < timedelta(minutes=30):
        mid = t0 + (t1 - t0) / 2
        ago = _ago(day.now_utc - mid)
        if fi:
            return "viimeisin keitto n. klo %s (%s sitten)" % (_hhmm(mid), ago)
        return "last brew ~%s (%s ago)" % (_hhmm(mid), ago)
    if fi:
        return "viimeisin havaittu keitto klo %s–%s" % (_hhmm(t0), _hhmm(t1))
    return "last brew detected between %s and %s" % (_hhmm(t0), _hhmm(t1))


def _pots_phrase(day, fi):
    parts = []
    for side, fi_name, en_name in (("left", "vasen", "left"), ("right", "oikea", "right")):
        u = day.usable[side]
        name = fi_name if fi else en_name
        if not u:
            parts.append(("%s ei lukemia" if fi else "%s no readings") % name)
        else:
            parts.append("%s %s" % (name, _half_cup_phrase(u[-1][1], fi)))
    return " · ".join(parts)


def build_caption(day):
    last = day.latest_reading_time()
    fi = "📈 Kahvitilanne tänään · viimeisin lukema klo %s\n%s · %s\n%s" % (
        _hhmm(last), _pots_phrase(day, True).capitalize(), _brew_phrase(day, True),
        "Viivan paksuus on mittausepävarmuus, noin puoli kuppia.")
    en = "Coffee today · last reading %s\n%s · %s\n%s" % (
        _hhmm(last), _pots_phrase(day, False).capitalize(), _brew_phrase(day, False),
        "The line is as thick as the measurement is uncertain — about half a cup.")
    return fi + "\n\n" + en


TEXT_DISABLED = "Kahvimittari ei ole käytössä. / The coffee reader is not enabled."

TEXT_EMPTY = ("Tänään ei ole vielä otettu yhtään kuvaa. Kokeile /status.\n"
              "No photos taken yet today. Try /status.")

TEXT_FAILED = ("Kuvaajan piirto epäonnistui. Kokeile hetken päästä uudelleen.\n"
               "Couldn't draw the graph. Try again in a moment.")


def _text_not_enough(n_readable):
    if n_readable == 1:
        fi_head = "Tänään on vain 1 luettava lukema, mikä ei riitä kuvaajaan."
        en_head = "Only 1 readable reading today — not enough for a graph."
    else:
        fi_head = ("Tänään on vain %d luettavaa lukemaa, mikä ei riitä kuvaajaan."
                   % n_readable)
        en_head = ("Only %d readable readings today — not enough for a graph."
                   % n_readable)
    return (fi_head
            + "\nKuvaaja piirtyy kun päivälle kertyy vähintään 3 lukemaa yli tunnin ajalta."
            + "\nPyydä /status useammin, niin kuvaajakin täyttyy."
            + "\n\n" + en_head
            + "\nA graph needs at least 3 readings spanning at least an hour."
            + "\nAsk for /status more often and the graph fills in.")


# ---------------------------------------------------------------------------
# fonts (§4.4)
# ---------------------------------------------------------------------------

def _load_fonts(font_dir=None):
    """DejaVu from font_dir, then the Debian path, then any system DejaVu/Arial,
    then Pillow's bitmap default — an ugly graph beats an exception."""
    candidates = []
    if font_dir:
        candidates.append((os.path.join(font_dir, "DejaVuSans.ttf"),
                           os.path.join(font_dir, "DejaVuSans-Bold.ttf")))
    candidates.append(("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                       "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"))
    candidates.append(("DejaVuSans.ttf", "DejaVuSans-Bold.ttf"))
    candidates.append(("arial.ttf", "arialbd.ttf"))
    sizes = {"title": 26, "axis": 20, "body": 18, "small": 16}
    for reg, bold in candidates:
        try:
            fonts = {k: ImageFont.truetype(reg, s) for k, s in sizes.items()}
            fonts["title"] = ImageFont.truetype(bold, sizes["title"])
            return fonts
        except (OSError, ValueError):
            continue
    f = ImageFont.load_default()
    return {k: f for k in sizes}


def _text(draw, xy, s, font, fill, anchor="ls"):
    """Anchored text via textbbox so old Pillows without anchor= still work.
    anchor: l/m/r horizontal + s(baseline)/t(top)/m(middle) vertical."""
    x, y = xy
    try:
        box = draw.textbbox((0, 0), s, font=font)
    except AttributeError:                      # pragma: no cover (Pillow < 8)
        w, h = draw.textsize(s, font=font)
        box = (0, 0, w, h)
    tw = box[2] - box[0]
    if anchor[0] == "m":
        x -= tw / 2.0
    elif anchor[0] == "r":
        x -= tw
    v = anchor[1]
    if v == "s":                                 # baseline sits ascent below draw-y
        try:
            y -= font.getmetrics()[0]
        except AttributeError:
            y -= box[3]
    elif v == "t":                               # visual ink top at y
        y -= box[1]
    elif v == "m":                               # visual ink middle at y
        y -= (box[1] + box[3]) / 2.0
    draw.text((x - box[0], y), s, font=font, fill=fill)
    return tw


# ---------------------------------------------------------------------------
# rendering (§6)
# ---------------------------------------------------------------------------

def _rgba(hex_colour, alpha):
    h = hex_colour.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), alpha)


def _floor_hour(dt):
    return dt.replace(minute=0, second=0, microsecond=0)


def _ceil_hour(dt):
    f = _floor_hour(dt)
    return f if f == dt else f + timedelta(hours=1)


def _dotted_line(draw, p0, p1, fill, width=2, on=4, off=6):
    (x0, y0), (x1, y1) = p0, p1
    length = ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
    if length < 1:
        return
    ux, uy = (x1 - x0) / length, (y1 - y0) / length
    d = 0.0
    while d < length:
        e = min(d + on, length)
        draw.line([(x0 + ux * d, y0 + uy * d), (x0 + ux * e, y0 + uy * e)],
                  fill=fill, width=width)
        d += on + off


def render_day_graph(day, font_dir=None):
    """Draw the 1000x640 chart for a gated DaySeries. Returns PNG bytes."""
    x0, y0, x1, y1 = PLOT
    now_local = day.now_utc.astimezone()
    events = day.all_event_times()
    first_local = min(t.astimezone() for t in events)
    t_start = _floor_hour(min(first_local, now_local.replace(hour=7, minute=0,
                                                             second=0, microsecond=0)))
    t_end = _ceil_hour(max(now_local + timedelta(minutes=30),
                           now_local.replace(hour=17, minute=0, second=0, microsecond=0)))
    span_s = (t_end - t_start).total_seconds()

    def X(t_utc):
        s = (t_utc.astimezone() - t_start).total_seconds()
        return x0 + (x1 - x0) * s / span_s

    def Y(ml):
        return y1 - ml * PX_PER_ML

    fonts = _load_fonts(font_dir)
    img = Image.new("RGBA", (W, H), BG)
    draw = ImageDraw.Draw(img)

    # 1. frame and gridlines
    for cups in range(1, 10, 2):                                   # minor, odd cups
        gy = Y(cups * CUP_ML)
        draw.line([(x0, gy), (x1, gy)], fill=GRID_MINOR, width=1)
    for cups in range(0, 11, 2):                                   # major, even cups
        gy = Y(cups * CUP_ML)
        draw.line([(x0, gy), (x1, gy)], fill=GRID_MAJOR, width=1)
        _text(draw, (84, gy), str(cups), fonts["axis"], TEXT_BODY, anchor="rm")
    draw.rectangle([x0, y0, x1, y1], outline=FRAME, width=2)

    # 2. brew bands, behind the data (§6.3)
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    for side in ("left", "right"):
        for t0, t1 in day.brews[side]:
            bx0, bx1 = max(X(t0), x0), min(X(t1), x1)
            if bx1 - bx0 < 3:                                      # keep it visible
                mid = (bx0 + bx1) / 2
                bx0, bx1 = mid - 1.5, mid + 1.5
            odraw.rectangle([bx0, y0, bx1, y1], fill=_rgba(BREW, 31))
            odraw.rectangle([bx0, y0, bx1, y0 + 2], fill=_rgba(BREW, 255))
    img = Image.alpha_composite(img, overlay)

    # 3. per-phase across pots: connectors, then bands, then lines, then markers,
    #    so overlapping translucent fills mix and neither centre line hides (§6.3)
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    seg_cache = {s: day.segments(s) for s in ("left", "right")}
    for side in ("left", "right"):
        segs = seg_cache[side]
        for a, b in zip(segs, segs[1:]):                           # gap connectors
            _dotted_line(odraw,
                         (X(a[-1][0]), Y(a[-1][1])),
                         (X(b[0][0]), Y(b[0][1])),
                         _rgba(COLOURS[side], 77))
    img = Image.alpha_composite(img, overlay)
    for side in ("left", "right"):                                 # uncertainty bands
        # one overlay per pot, composited in turn, so the two pots' translucent
        # fills genuinely mix where they overlap (§6.3)
        overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        odraw = ImageDraw.Draw(overlay)
        band = _rgba(COLOURS[side], 115)
        for seg in seg_cache[side]:
            if len(seg) == 1:
                t, ml = seg[0]
                cx, cy0, cy1 = X(t), Y(ml + ERROR_ML), Y(ml - ERROR_ML)
                odraw.ellipse([cx - 6, max(cy0, y0), cx + 6, min(cy1, y1)], fill=band)
            else:
                upper = [(X(t), max(Y(ml + ERROR_ML), y0)) for t, ml in seg]
                lower = [(X(t), min(Y(ml - ERROR_ML), y1)) for t, ml in reversed(seg)]
                odraw.polygon(upper + lower, fill=band)
        img = Image.alpha_composite(img, overlay)
    draw = ImageDraw.Draw(img)
    dense = sum(len(u) for u in day.usable.values()) > 500         # sampler-era days
    for side in ("left", "right"):                                 # centre lines
        for seg in seg_cache[side]:
            if len(seg) >= 2:
                draw.line([(X(t), Y(ml)) for t, ml in seg],
                          fill=COLOURS[side], width=2, joint="curve")
    if not dense:                                                  # reading markers
        for side in ("left", "right"):
            for seg in seg_cache[side]:
                for t, ml in seg:
                    cx, cy = X(t), Y(ml)
                    draw.ellipse([cx - 3, cy - 3, cx + 3, cy + 3], fill=COLOURS[side])

    # 4. x ticks and hour labels
    tick_h = t_start
    while tick_h <= t_end:
        tx = x0 + (x1 - x0) * (tick_h - t_start).total_seconds() / span_s
        draw.line([(tx, y1 + 1), (tx, y1 + 7)], fill=FRAME, width=2)
        tick_h += timedelta(hours=1)
    label_h = t_start if t_start.hour % 2 == 0 else t_start + timedelta(hours=1)
    while label_h <= t_end:
        tx = x0 + (x1 - x0) * (label_h - t_start).total_seconds() / span_s
        _text(draw, (tx, 528), str(label_h.hour), fonts["body"], TEXT_BODY, anchor="mt")
        label_h += timedelta(hours=2)

    # 5. rug rows (§2.3) — shifted 6 px below the spec table so 18 px hour
    #    labels fit between the frame and the rug
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    rows = {"left": (540, 552), "right": (556, 568)}
    for side, (ry0, ry1) in rows.items():
        label = "V/L" if side == "left" else "O/R"
        _text(draw, (60, (ry0 + ry1) / 2), label, fonts["small"], TEXT_DIM, anchor="lm")
        for t, kind in day.rug[side]:
            rx = X(t)
            if rx < x0 or rx > x1:
                continue
            if kind == "abstain":
                odraw.rectangle([rx - 1, ry0 + 1, rx + 1, ry1 - 1],
                                fill=_rgba(COLOURS[side], 140))
            else:                                                  # absent: not detected
                cy = (ry0 + ry1) / 2
                odraw.ellipse([rx - 2, cy - 2, rx + 2, cy + 2],
                              fill=_rgba(RUG_ABSENT, 255))
    img = Image.alpha_composite(img, overlay)
    draw = ImageDraw.Draw(img)

    # 6. title block, legend, footer
    _text(draw, (24, 34), "Kahvia kiltiksellä tänään · Coffee today",
          fonts["title"], TEXT_DARK)
    date_s = "%s %d.%d." % (FI_WEEKDAYS[now_local.weekday()],
                            now_local.day, now_local.month)
    _text(draw, (976, 34), date_s, fonts["body"], TEXT_DIM, anchor="rs")
    _text(draw, (24, 62),
          "%d luettavaa lukemaa %d kuvasta · %d readable of %d photos"
          % (day.n_readable, day.n_photos, day.n_readable, day.n_photos),
          fonts["body"], TEXT_DIM)
    _text(draw, (16, 80), "kuppia", fonts["small"], TEXT_DIM)
    _text(draw, (16, 96), "cups", fonts["small"], TEXT_DIM)

    # row 1: what the lines are; row 2: what the marks are
    lx = 24
    for side, label in (("left", "vasen levy / left plate"),
                        ("right", "oikea levy / right plate")):
        draw.rectangle([lx, 578, lx + 22, 588], fill=COLOURS[side])
        suffix = "" if day.usable[side] else " (ei lukemia / no readings)"
        tw = _text(draw, (lx + 30, 588), label + suffix, fonts["body"], TEXT_BODY)
        lx += 30 + tw + 28
    lx = 24
    draw.rectangle([lx, 600, lx + 22, 610], fill=_rgba(BREW, 90))
    draw.rectangle([lx, 600, lx + 22, 602], fill=BREW)
    tw = _text(draw, (lx + 30, 610), "havaittu keitto / brew detected",
               fonts["body"], TEXT_BODY)
    lx += 30 + tw + 28
    draw.rectangle([lx + 4, 600, lx + 6, 610], fill=_rgba(COLOURS["left"], 140))
    _text(draw, (lx + 14, 610), "ei lukemaa / no reading",
          fonts["body"], TEXT_BODY)
    _text(draw, (24, 630),
          "Viivan paksuus = epävarmuus, katkoviiva = ei lukemia · "
          "line thickness = uncertainty, dashed = no readings",
          fonts["small"], TEXT_FOOT)

    buf = io.BytesIO()
    img.convert("RGB").save(buf, "PNG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------

def graph_reply(log_pattern, now_utc=None, font_dir=None):
    """Everything /graph needs: (png_bytes or None, caption/fallback text).

    The caller wraps this in try/except and falls back to TEXT_FAILED —
    the failure discipline is read_coffee_level()'s (§4.2)."""
    if not log_pattern:
        return None, TEXT_DISABLED
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    now_local = now_utc.astimezone()
    path = now_local.strftime(log_pattern)
    try:
        stat = os.stat(path)
        mtime = stat.st_mtime
    except OSError:
        return None, TEXT_EMPTY

    records = load_today(log_pattern, now_utc)
    if not records:
        return None, TEXT_EMPTY
    day = DaySeries(records, now_utc)
    if not day.enough_for_graph():
        return None, _text_not_enough(day.n_readable)

    key = (path, now_local.date().isoformat(), mtime, len(records))
    if _cache["key"] == key:                                       # §4.3
        return _cache["png"], _cache["caption"]
    png = render_day_graph(day, font_dir=font_dir)
    caption = build_caption(day)
    _cache.update(key=key, png=png, caption=caption)
    return png, caption
