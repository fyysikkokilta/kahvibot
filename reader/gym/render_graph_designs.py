"""Render candidate /graph designs on real guild-room data, for visual choice.

Data: the Pi's own reading log (33 s cadence) and the two smart plugs, both from
2026-09-15, including the two brews at 14:58 local.

The grey band is produced by the real filter (pipeline/rbpf.py), fed one Gaussian
measurement per reading. The per-reading width comes from the entropy -> posterior
sd relation measured on archived frames (37 ml below 0.55, 60 ml to 0.68, 240 ml
above), because the log keeps entropy but not the frames, so the calibrated
density head cannot be re-run on them. Once the reader service is deployed the
band comes straight from the head and this approximation disappears.
"""
import json
import math
import pathlib
import sys
from datetime import datetime, timedelta, timezone

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Rectangle

READER = pathlib.Path(r"C:\Users\Käyttäjä\documents\projects\lifestyle\coffee\kahvibot\reader")
sys.path.insert(0, str(READER))
from pipeline.rbpf import Calibration, PotRBPF  # noqa: E402
from pipeline.reader import row_dist  # noqa: E402

S = pathlib.Path(r"C:\Users\KYTTJ~1\AppData\Local\Temp\claude\C--Users-K-ytt-j--documents-projects-lifestyle-coffee\43a96958-cbdd-49cd-8fa3-f6348b29dfd2\scratchpad")
OUT = pathlib.Path(r"C:\Users\Käyttäjä\documents\projects\lifestyle\coffee\graph_proposals")
OUT.mkdir(exist_ok=True)

# kahvibot palette (graphs.py §5.5)
BG, FRAME = "#fbfaf8", "#c9c4bc"
GRID_MAJOR, GRID_MINOR = "#e3e0da", "#efede8"
DARK, BODY, DIM, FOOT = "#1a1a1a", "#2b2b2b", "#5a5a5a", "#6a6a6a"
COL = {"left": "#1f77b4", "right": "#e07b00"}
BREW = "#2ca02c"
BAND = "#b9b3ab"
FI = {"left": "VASEN", "right": "OIKEA"}
CUP_ML = 125.0
HOURS = 3.0
ROWS, Y_BASE, Y_TOP = 256, 0.88, 0.12
CAL = Calibration(READER / "models" / "calibration.json")


def sd_from_entropy(e):
    """Posterior sd in ml, from the archive measurement. Documented approximation."""
    return float(np.clip(math.exp(3.62 + 6.0 * (e - 0.52)), 15.0, 400.0))


def gaussian_rowdist(h, sd_ml):
    """A measurement of this fill with this spread, in the shape the filter wants."""
    sd_h = max(sd_ml / 1250.0, 1e-3)
    span = Y_BASE - Y_TOP
    row = (Y_BASE - h * span) * (ROWS - 1)
    sd_rows = max(sd_h * span * (ROWS - 1), 0.8)
    g = np.arange(ROWS, dtype=float)
    logits = np.zeros((3, ROWS))
    logits[2] = -0.5 * ((g - row) / sd_rows) ** 2
    return row_dist(logits, Y_BASE, Y_TOP)


def load():
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
    return recs, power


def power_at(rows, t):
    """Last reported wattage at or before t (plugs report on change)."""
    v = None
    for ts, w in rows:
        if ts <= t:
            v = w
        else:
            break
    return v


def run_filter(recs, power, side, t_from):
    f = PotRBPF(CAL, n_particles=1200, seed=7)
    out = []
    prev = None
    for t, pots in recs:
        q = next((p for p in pots if p["s"] == side), None)
        dt = 0.0 if prev is None else (t - prev).total_seconds()
        prev = t
        rd = None
        if q is not None and q.get("h") is not None:
            rd = gaussian_rowdist(q["h"], sd_from_entropy(q.get("e", 0.6)))
        post = f.step(dt=min(dt, 300.0), power_w=power_at(power[side], t), rowdist=rd,
                      surface_logit=2.0)
        if t >= t_from:
            out.append((t, post.ml_median, post.ml_lo, post.ml_hi, post.temp_mean,
                        post.p_brewing))
    return out


def loc(t):
    """Guild-room wall time. The log is UTC; an axis labelled 12:00 for a
    15:00 brew is worse than no axis at all."""
    return t.astimezone().replace(tzinfo=None)


def style(ax, labelsize=11):
    ax.set_facecolor(BG)
    for s in ax.spines.values():
        s.set_color(FRAME); s.set_linewidth(1.1)
    ax.tick_params(colors=BODY, labelsize=labelsize)
    ax.grid(True, which="major", color=GRID_MAJOR, linewidth=0.9)
    ax.grid(True, which="minor", color=GRID_MINOR, linewidth=0.6)


def cups_text(ml):
    """Whole cups. No fractions: a half-cup glyph is wide, collides with the
    label beside it, and is a precision the reader cannot honestly claim."""
    return str(int(round(ml / CUP_ML)))


def brew_spans(power_rows, t0, t1, threshold=800.0):
    t0, t1 = (t0.astimezone().replace(tzinfo=None), t1.astimezone().replace(tzinfo=None))
    spans, start = [], None
    for ts, w in power_rows:
        if start is None and w >= threshold:
            start = ts
        elif start is not None and w < 600.0:
            spans.append((start, ts)); start = None
    if start is not None:
        spans.append((start, t1))
    spans = [(a.astimezone().replace(tzinfo=None), b.astimezone().replace(tzinfo=None)) for a, b in spans]
    return [(max(a, t0), min(b, t1)) for a, b in spans if b >= t0 and a <= t1]


# --------------------------------------------------------------------------
def variant_a(series, power, t0, t1, now, lt0, lt1):
    """Two stacked pot panels, each with its own power strip. Numbers on the left."""
    fig = plt.figure(figsize=(10, 8.0), dpi=100)
    fig.patch.set_facecolor(BG)
    gs = fig.add_gridspec(4, 3, height_ratios=[3.2, 0.95, 3.2, 0.95],
                          width_ratios=[1.5, 3.3, 3.3], hspace=0.20, wspace=0.10,
                          left=0.025, right=0.975, top=0.895, bottom=0.055)
    fig.text(0.03, 0.965, "Kiltiksen kahvi", fontsize=28,
             fontweight="bold", color=DARK, va="top")
    fig.text(0.975, 0.965, now.strftime("3 h  ·  %d.%m. klo %H:%M"), ha="right", va="top",
             fontsize=19, color=DIM)

    for i, side in enumerate(("left", "right")):
        s = series[side]
        t = [loc(x[0]) for x in s]
        med = np.array([x[1] for x in s]); lo = np.array([x[2] for x in s]); hi = np.array([x[3] for x in s])

        # big number block
        axn = fig.add_subplot(gs[2 * i, 0]); axn.axis("off")
        axn.text(0.0, 0.60, cups_text(med[-1]), fontsize=64, fontweight="bold",
                 color=COL[side], va="center", ha="left")
        axn.text(0.0, 0.22, f"{med[-1]:.0f} ml", fontsize=32, fontweight="bold",
                 color=DARK, va="center", ha="left")
        axn.text(0.0, 0.97, FI[side], fontsize=24, fontweight="bold", color=DIM,
                 va="center", ha="left")

        ax = fig.add_subplot(gs[2 * i, 1:]); style(ax, 22)
        ax.fill_between(t, lo, hi, color=BAND, alpha=0.45, linewidth=0,
                        label="95 % luottamusväli")
        ax.plot(t, med, color=COL[side], linewidth=5.2)
        for a, b in brew_spans(power[side], t0, t1):
            ax.axvspan(a, b, color=BREW, alpha=0.13, zorder=0)
        ax.set_ylim(0, 1300); ax.set_xlim(lt0, lt1)
        ax.set_yticks([0, 250, 500, 750, 1000, 1250])
        ax.set_yticklabels(["0", "2", "4", "6", "8", "10"], fontsize=22)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
        ax.set_xticklabels([])

        axp = fig.add_subplot(gs[2 * i + 1, 1:]); style(axp, 20)
        pw = [(loc(ts), w) for ts, w in power[side] if t0 <= ts <= t1]
        if pw:
            axp.plot([p[0] for p in pw], [max(p[1], 1.0) for p in pw], color=BODY,
                     linewidth=3.0, drawstyle="steps-post")
        # log scale keeps standby, hotplate and element all visible at once; the
        # axis itself is dropped because the shape is the message, not the watts
        axp.set_yscale("log"); axp.set_ylim(1, 3000); axp.set_xlim(lt0, lt1)
        axp.set_yticks([])
        axp.axhline(800, color=BREW, linewidth=1, linestyle=":")
        for a, b in brew_spans(power[side], t0, t1):
            axp.axvspan(a, b, color=BREW, alpha=0.13, zorder=0)
        axp.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
        if i == 0:
            axp.set_xticklabels([])
    fig.savefig(OUT / "A_stacked.png", facecolor=BG)
    plt.close(fig)


def variant_b(series, power, t0, t1, now, lt0, lt1):
    """One column per pot: huge number, level, power. Reads top-down per machine."""
    fig = plt.figure(figsize=(10, 7.2), dpi=100)
    fig.patch.set_facecolor(BG)
    gs = fig.add_gridspec(3, 2, height_ratios=[1.35, 3.0, 1.05], hspace=0.22, wspace=0.16,
                          left=0.07, right=0.97, top=0.90, bottom=0.08)
    fig.text(0.07, 0.965, "Kiltiksen kahvi — viimeiset 3 h", fontsize=19,
             fontweight="bold", color=DARK, va="top")
    fig.text(0.97, 0.965, now.strftime("%a %d.%m. klo %H:%M"), ha="right", va="top",
             fontsize=11, color=DIM)

    for i, side in enumerate(("left", "right")):
        s = series[side]
        t = [loc(x[0]) for x in s]
        med = np.array([x[1] for x in s]); lo = np.array([x[2] for x in s]); hi = np.array([x[3] for x in s])

        axn = fig.add_subplot(gs[0, i]); axn.axis("off")
        axn.text(0.5, 1.02, FI[side], fontsize=15, fontweight="bold", color=DIM,
                 ha="center", va="top")
        axn.text(0.5, 0.44, cups_text(med[-1]), fontsize=72, fontweight="bold",
                 color=COL[side], ha="center", va="center")
        axn.text(0.5, 0.02, f"kuppia  ·  {med[-1]:.0f} ml  ·  ± {(hi[-1]-lo[-1])/2:.0f} ml",
                 fontsize=12, color=BODY, ha="center", va="bottom")

        ax = fig.add_subplot(gs[1, i]); style(ax)
        ax.fill_between(t, lo, hi, color=BAND, alpha=0.45, linewidth=0)
        ax.plot(t, med, color=COL[side], linewidth=2.8)
        for a, b in brew_spans(power[side], t0, t1):
            ax.axvspan(a, b, color=BREW, alpha=0.13, zorder=0)
        ax.set_ylim(0, 1300); ax.set_xlim(lt0, lt1)
        ax.set_yticks([0, 250, 500, 750, 1000, 1250])
        ax.set_yticklabels(["0", "2", "4", "6", "8", "10"] if i == 0 else [], fontsize=13)
        if i == 0:
            ax.set_ylabel("kuppia", color=BODY, fontsize=12)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
        ax.set_xticklabels([])

        axp = fig.add_subplot(gs[2, i]); style(axp)
        pw = [(loc(ts), w) for ts, w in power[side] if t0 <= ts <= t1]
        if pw:
            axp.plot([p[0] for p in pw], [max(p[1], 1.0) for p in pw], color=BODY,
                     linewidth=1.6, drawstyle="steps-post")
        axp.set_yscale("log"); axp.set_ylim(1, 3000); axp.set_xlim(lt0, lt1)
        axp.set_yticks([1, 100, 1000]); axp.set_yticklabels(["1", "100", "1k"] if i == 0 else [], fontsize=10)
        axp.axhline(800, color=BREW, linewidth=1, linestyle=":")
        for a, b in brew_spans(power[side], t0, t1):
            axp.axvspan(a, b, color=BREW, alpha=0.13, zorder=0)
        if i == 0:
            axp.set_ylabel("teho W", color=BODY, fontsize=11)
        axp.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    fig.text(0.07, 0.02, "harmaa = mallin 95 % epävarmuus · vihreä = keitto käynnissä",
             fontsize=9.5, color=FOOT)
    fig.savefig(OUT / "B_columns.png", facecolor=BG)
    plt.close(fig)


def variant_c(series, power, t0, t1, now, lt0, lt1):
    """Answer-first: the numbers carry the message, the curves are supporting
    sparklines. Aimed squarely at 'faster to read than the photo'."""
    fig = plt.figure(figsize=(10, 6.0), dpi=100)
    fig.patch.set_facecolor(BG)
    gs = fig.add_gridspec(2, 2, height_ratios=[1.0, 1.0], hspace=0.30, wspace=0.12,
                          left=0.05, right=0.97, top=0.88, bottom=0.10)
    fig.text(0.05, 0.955, "Kiltiksen kahvi", fontsize=21, fontweight="bold",
             color=DARK, va="top")
    fig.text(0.97, 0.955, now.strftime("%a %d.%m. klo %H:%M"), ha="right", va="top",
             fontsize=11, color=DIM)

    for i, side in enumerate(("left", "right")):
        s = series[side]
        t = [loc(x[0]) for x in s]
        med = np.array([x[1] for x in s]); lo = np.array([x[2] for x in s]); hi = np.array([x[3] for x in s])
        spans = brew_spans(power[side], t0, t1)
        ax = fig.add_subplot(gs[i, :]); ax.axis("off")
        ax.set_xlim(0, 1); ax.set_ylim(0, 1)
        ax.add_patch(Rectangle((0, 0), 1, 1, facecolor="white", edgecolor=FRAME,
                               linewidth=1.1, transform=ax.transAxes, zorder=0))
        ax.text(0.022, 0.80, FI[side], fontsize=15, fontweight="bold", color=DIM, va="center")
        ax.text(0.030, 0.40, cups_text(med[-1]), fontsize=58, fontweight="bold",
                color=COL[side], va="center")
        ax.text(0.215, 0.52, "kuppia", fontsize=16, color=BODY, va="center")
        ax.text(0.215, 0.30, f"{med[-1]:.0f} ml ± {(hi[-1]-lo[-1])/2:.0f}", fontsize=13,
                color=DIM, va="center")
        when = "keittää nyt" if spans and spans[-1][1] >= lt1 - timedelta(minutes=1) else (
            f"keitetty {int((lt1 - spans[-1][1]).total_seconds() // 60)} min sitten"
            if spans else "ei keittoa 3 h:ssa")
        ax.text(0.315, 0.74, when, fontsize=14, color=BODY, va="center")
        ax.text(0.315, 0.50, f"noin {s[-1][4]:.0f} °C", fontsize=14, color=DIM, va="center")

        sub = ax.inset_axes([0.545, 0.16, 0.435, 0.70])
        style(sub); sub.set_facecolor("white")
        sub.fill_between(t, lo, hi, color=BAND, alpha=0.45, linewidth=0)
        sub.plot(t, med, color=COL[side], linewidth=2.6)
        for a, b in spans:
            sub.axvspan(a, b, color=BREW, alpha=0.16, zorder=0)
        sub.set_ylim(0, 1300); sub.set_xlim(lt0, lt1)
        sub.set_yticks([0, 625, 1250]); sub.set_yticklabels(["0", "5", "10"], fontsize=11)
        sub.grid(True, color=GRID_MAJOR, linewidth=0.8)
        sub.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
        sub.tick_params(labelsize=10)
    fig.text(0.05, 0.03, "3 h · harmaa = 95 % epävarmuus · vihreä = keitto",
             fontsize=9.5, color=FOOT)
    fig.savefig(OUT / "C_answer_first.png", facecolor=BG)
    plt.close(fig)


def main():
    recs, power = load()
    now = recs[-1][0]
    t1 = now
    t0 = now - timedelta(hours=HOURS)
    series = {s: run_filter(recs, power, s, t0) for s in ("left", "right")}
    for s in ("left", "right"):
        n = len(series[s])
        last = series[s][-1]
        print(f"{s:5s}: {n} points in window, now {last[1]:.0f} ml "
              f"[{last[2]:.0f}, {last[3]:.0f}], {last[4]:.0f} C")
    lt0, lt1 = loc(t0), loc(t1)
    variant_a(series, power, t0, t1, now.astimezone(), lt0, lt1)
    variant_b(series, power, t0, t1, now.astimezone(), lt0, lt1)
    variant_c(series, power, t0, t1, now.astimezone(), lt0, lt1)
    for p in sorted(OUT.glob("*.png")):
        print("wrote", p, f"{p.stat().st_size // 1024} kB")


if __name__ == "__main__":
    main()
