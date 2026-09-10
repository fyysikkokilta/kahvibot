import json
import re
import threading
from datetime import datetime

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, Rectangle
import numpy as np
import pandas as pd

from config import (
    DATA_DIR,
    DEFAULT_DEVICE,
    BREW_THRESHOLD,
    HEAT,
    CUP_CALIBRATION,
    DEVICES,
)

_DEVICE_RE = re.compile(r"^[A-Za-z0-9_-]+$")

# kahvibot-style palette (fk/kahvibot/graphs.py): warm paper background,
# subtle two-tone grid, boxed frame, brew highlights in green.
BG = "#fbfaf8"
FRAME = "#c9c4bc"
GRID_MAJOR = "#e3e0da"
GRID_MINOR = "#efede8"
TEXT_DARK = "#1a1a1a"
TEXT_BODY = "#2b2b2b"
TEXT_DIM = "#5a5a5a"
TEXT_FOOT = "#6a6a6a"
BREW = "#2ca02c"
DEVICE_COLORS = {"vasen": "#1f77b4", "oikea": "#e07b00"}

CALIBRATION_FILE = "calibration.json"

_plot_cache = {}
_render_lock = threading.Lock()


# --- brew-size calibration store ---------------------------------------------
# Points are (duration_seconds, cups) pairs. They come from the CUP_CALIBRATION
# config value if set, otherwise from data/calibration.json (written by
# calibrate.py). A linear fit through the points is used by estimate_cups.

def _calibration_path():
    return DATA_DIR / CALIBRATION_FILE


def load_calibration():
    points = list(CUP_CALIBRATION)
    if points:
        return [tuple(p) for p in points]
    path = _calibration_path()
    if path.is_file():
        try:
            data = json.loads(path.read_text())
            points = [(float(s), float(c)) for s, c in data.get("points", [])]
        except (ValueError, TypeError, OSError):
            points = []
    return sorted(points)


def save_calibration(points):
    path = _calibration_path()
    path.parent.mkdir(exist_ok=True)
    data = {
        "points": [[float(s), float(c)] for s, c in points],
        "updated": pd.Timestamp.now().isoformat(),
    }
    path.write_text(json.dumps(data, indent=2) + "\n")
    return path


def get_csv_path(device=DEFAULT_DEVICE):
    if not _DEVICE_RE.match(device):
        raise ValueError(f"Invalid device name: {device!r}")
    return DATA_DIR / f"power_{device}.csv"


def _hysteresis_events(df, start_threshold, end_threshold):
    """Brews as (start, end, peak, duration) dicts.

    Same rule as before: a brew starts at the first sample above start_threshold
    and ends at the first later sample below end_threshold; a brew still running
    at the end of the data is reported up to the last sample. Only the samples
    that can change the state are visited, so a 150k-row CSV costs a few hundred
    iterations instead of a pandas iterrows() over every row (tens of seconds on
    a Raspberry Pi, once per /brew or /plot).
    """
    if df.empty:
        return []
    ts = df["timestamp"].reset_index(drop=True)
    power = pd.to_numeric(df["power"], errors="coerce").to_numpy(dtype=float)
    above = power > start_threshold
    below = power < end_threshold

    def event(i0, i1):
        return {
            "start": ts.iloc[i0],
            "end": ts.iloc[i1],
            "peak": float(np.nanmax(power[i0:i1 + 1])),
            "duration": ts.iloc[i1] - ts.iloc[i0],
        }

    events = []
    start_i = None
    for i in np.flatnonzero(above | below):
        if start_i is None:
            if above[i]:
                start_i = int(i)
        elif below[i]:
            events.append(event(start_i, int(i)))
            start_i = None
    if start_i is not None:
        events.append(event(start_i, len(power) - 1))
    return events


def _normalize_local(ts):
    """Return the series as naive local wall time.

    mqtt_logger writes UTC timestamps with an explicit offset, while CSVs
    written before that change hold naive local wall time. Convert any
    tz-aware values to local wall time (dropping tzinfo) so comparisons
    against naive ``pd.Timestamp.now()`` work regardless of the mix.
    """
    if ts.dtype == "object":
        return ts.apply(_ts_to_local_naive)
    if ts.dt.tz is not None:
        return ts.dt.tz_convert(_localtz()).dt.tz_localize(None)
    return ts


def _localtz():
    # stdlib: pd.Timestamp.now().astimezone() is broken on pandas 3.0
    return datetime.now().astimezone().tzinfo


def _ts_to_local_naive(ts):
    if ts.tzinfo is None:
        return ts
    return ts.tz_convert(_localtz()).tz_localize(None)


def detect_brews(device=DEFAULT_DEVICE, start_threshold=BREW_THRESHOLD, end_threshold=HEAT):
    csv_path = get_csv_path(device)
    if not csv_path.is_file():
        return []
    df = pd.read_csv(csv_path)
    if df.empty or "power" not in df.columns:
        return []
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df["timestamp"] = _normalize_local(df["timestamp"])
    df = df.dropna(subset=["timestamp"])
    if df.empty:
        return []
    return _hysteresis_events(df, start_threshold, end_threshold)


def last_brew(device=DEFAULT_DEVICE, start_threshold=BREW_THRESHOLD, end_threshold=HEAT):
    brews = detect_brews(device, start_threshold, end_threshold)
    return brews[-1] if brews else None


def fmt_duration(td):
    total = int(td.total_seconds())
    if total < 0:
        return ""
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m:02d}m"
    if m:
        return f"{m}m {s:02d}s"
    return f"{s}s"


def estimate_cups(duration):
    """Estimate cup count from brew duration via linear calibration.

    Assumes the machine draws roughly constant power for as long as water is
    still passing through, so brew duration scales with the amount of water.
    Returns None if no calibration points are configured.
    """
    if not load_calibration():
        return None
    seconds = duration.total_seconds() if hasattr(duration, "total_seconds") else duration
    points = sorted(load_calibration())
    if len(points) == 1:
        ref_secs, ref_cups = points[0]
        if ref_secs <= 0:
            return None
        cups = seconds * (ref_cups / ref_secs)
    else:
        secs_arr, cups_arr = zip(*points)
        slope, intercept = np.polyfit(secs_arr, cups_arr, 1)
        cups = slope * seconds + intercept
    return max(cups, 0.0)


def brew_summary(brew, now=None):
    if brew is None:
        return f"☕ No brews detected yet (power never exceeded {BREW_THRESHOLD:.0f} W)"
    now = pd.Timestamp.now() if now is None else now
    end = brew["end"]
    ongoing = end >= now - pd.Timedelta(seconds=90)
    when = "brewing right now" if ongoing else f"{fmt_duration(now - end)} ago"
    cups = estimate_cups(brew["duration"])
    cups_str = f" · ~{cups:.1f} cups" if cups is not None else ""
    return (
        f"☕ Last brew: {when}\n"
        f"   {end.strftime('%H:%M')} · {fmt_duration(brew['duration'])}{cups_str}"
    )


def plot_power(device=DEFAULT_DEVICE, out_png=None):
    """Render (or return the cached) power plot for the device since midnight.

    The plot is keyed on the CSV's mtime/size, so it is only re-rendered when
    new rows arrive; repeated /plot calls reuse the same PNG.
    """
    csv_path = get_csv_path(device)
    if not csv_path.is_file():
        raise FileNotFoundError(f"No data for {device}")
    if out_png is None:
        out_png = DATA_DIR / f"plot_{device}.png"
    stat = csv_path.stat()
    key = (str(csv_path), stat.st_mtime_ns, stat.st_size, str(out_png))
    with _render_lock:
        if key in _plot_cache:
            return _plot_cache[key]
        path = _render_power(csv_path, device, out_png)
        _plot_cache[key] = path
    return path


def _render_power(csv_path, device, out_png):
    df = pd.read_csv(csv_path)
    if df.empty or "timestamp" not in df.columns or "power" not in df.columns:
        raise FileNotFoundError(f"No data for {device}")
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df["timestamp"] = _normalize_local(df["timestamp"])
    df["power"] = pd.to_numeric(df["power"], errors="coerce")
    df = df.dropna(subset=["timestamp", "power"])
    now = pd.Timestamp.now()
    df = df[df["timestamp"] >= now.normalize()]
    if df.empty:
        raise FileNotFoundError(f"No data for {device} since midnight")
    y = df["power"].clip(lower=1.0)

    series_color = DEVICE_COLORS.get(device, TEXT_BODY)
    brews = _hysteresis_events(df, BREW_THRESHOLD, HEAT)

    fig, ax = plt.subplots(figsize=(10, 6.4))
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)

    # brew bands behind the data, with a solid top edge (fk style)
    for br in brews:
        ax.axvspan(br["start"], br["end"], color=BREW, alpha=0.10, zorder=0)
        ax.add_patch(
            Rectangle(
                (mdates.date2num(br["start"]), 0.996),
                mdates.date2num(br["end"]) - mdates.date2num(br["start"]),
                0.004,
                transform=ax.get_xaxis_transform(),
                facecolor=BREW,
                linewidth=0,
                zorder=0,
            )
        )

    ax.axhline(BREW_THRESHOLD, color=TEXT_DIM, linewidth=1, linestyle=":", zorder=1)
    ax.plot(df["timestamp"], y, color=series_color, linewidth=1.4, zorder=2)
    if len(df) < 400:
        ax.plot(
            df["timestamp"], y, color=series_color,
            marker="o", markersize=2.6, linewidth=0, zorder=3,
        )

    ax.set_yscale("log")
    ax.set_ylim(bottom=1.0)
    # Fix the x-axis to the "since midnight" window. matplotlib pads a
    # zero-width datetime range by ~5% of the epoch-day value (~1600 days
    # today), which makes the hourly minor locator try to generate tens of
    # thousands of ticks. A bounded, non-empty range avoids that.
    x0 = now.normalize()
    ax.set_xlim(x0, max(now, x0 + pd.Timedelta(minutes=1)))
    ax.set_xlabel("time", color=TEXT_BODY)
    ax.set_ylabel("power (W, log)", color=TEXT_BODY)

    # title block: bold dark title, date right, dim sub-line
    label = "brew" if len(brews) == 1 else "brews"
    fig.text(
        0.08, 0.955, f"{device.capitalize()} — power usage since midnight",
        fontsize=15, fontweight="bold", color=TEXT_DARK, va="top",
    )
    fig.text(0.985, 0.955, now.strftime("%a %d.%m."), ha="right",
             va="top", fontsize=10, color=TEXT_DIM)
    fig.text(
        0.08, 0.91, f"{len(brews)} {label} detected · threshold {BREW_THRESHOLD:.0f} W",
        fontsize=9, color=TEXT_DIM, va="top",
    )

    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax.xaxis.set_minor_locator(mdates.HourLocator())
    ax.grid(True, which="major", color=GRID_MAJOR, linewidth=0.9)
    ax.grid(True, which="minor", color=GRID_MINOR, linewidth=0.6)

    for spine in ax.spines.values():
        spine.set_color(FRAME)
        spine.set_linewidth(1.2)

    ax.tick_params(axis="both", colors=TEXT_BODY, labelsize=9)
    ax.tick_params(axis="y", which="minor", length=0)
    ax.tick_params(axis="x", which="minor", length=4, color=FRAME)

    legend = [
        Line2D([0], [0], color=series_color, linewidth=1.6, label=device),
        Patch(facecolor=BREW, alpha=0.25, label="brew detected"),
        Line2D([0], [0], color=TEXT_DIM, linewidth=1, linestyle=":",
               label=f"brew threshold {BREW_THRESHOLD:.0f} W"),
    ]
    fig.subplots_adjust(left=0.08, right=0.985, top=0.86, bottom=0.12)
    fig.legend(handles=legend, loc="lower center", ncol=3, frameon=False,
               fontsize=9, bbox_to_anchor=(0.5, 0.055))
    fig.text(0.5, 0.02, "y-axis log · shaded band = brew above threshold",
             ha="center", fontsize=8, color=TEXT_FOOT)

    fig.savefig(out_png, dpi=100)
    plt.close(fig)
    return out_png


def _today_df(device, now):
    """Today's samples for a device, or None if none since midnight."""
    path = get_csv_path(device)
    if not path.is_file():
        return None
    df = pd.read_csv(path)
    if df.empty or "power" not in df.columns:
        return None
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df["timestamp"] = _normalize_local(df["timestamp"])
    df["power"] = pd.to_numeric(df["power"], errors="coerce")
    df = df.dropna(subset=["timestamp", "power"])
    today = df[df["timestamp"] >= now.normalize()]
    return today if not today.empty else None


def plot_all(devices=None, out_png=None):
    """Overlay today's data for several devices on one PNG (cached like
    plot_power, keyed on all involved CSVs)."""
    if devices is None:
        devices = DEVICES
    if out_png is None:
        out_png = DATA_DIR / "plot_all.png"
    stats = []
    for device in devices:
        path = get_csv_path(device)
        if path.is_file():
            st = path.stat()
            stats.append((str(path), st.st_mtime_ns, st.st_size))
        else:
            stats.append((str(path), None))
    key = (tuple(stats), str(out_png))
    with _render_lock:
        if key in _plot_cache:
            return _plot_cache[key]
        path = _render_all(devices, out_png)
        _plot_cache[key] = path
    return path


def _render_all(devices, out_png):
    now = pd.Timestamp.now()
    series = [(d, df) for d in devices if (df := _today_df(d, now)) is not None]
    if not series:
        raise FileNotFoundError("No data for any device since midnight")

    fig, ax = plt.subplots(figsize=(10, 6.4))
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)

    ax.axhline(BREW_THRESHOLD, color=TEXT_DIM, linewidth=1, linestyle=":", zorder=1)
    for device, df in series:
        y = df["power"].clip(lower=1.0)
        color = DEVICE_COLORS.get(device, TEXT_BODY)
        ax.plot(df["timestamp"], y, color=color, linewidth=1.4, zorder=2)
        if len(df) < 400:
            ax.plot(
                df["timestamp"], y, color=color,
                marker="o", markersize=2.6, linewidth=0, zorder=3,
            )

    ax.set_yscale("log")
    ax.set_ylim(bottom=1.0)
    x0 = now.normalize()
    ax.set_xlim(x0, max(now, x0 + pd.Timedelta(minutes=1)))
    ax.set_xlabel("time", color=TEXT_BODY)
    ax.set_ylabel("power (W, log)", color=TEXT_BODY)

    fig.text(
        0.08, 0.955, "Power usage since midnight — all devices",
        fontsize=15, fontweight="bold", color=TEXT_DARK, va="top",
    )
    fig.text(0.985, 0.955, now.strftime("%a %d.%m."), ha="right",
             va="top", fontsize=10, color=TEXT_DIM)

    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax.xaxis.set_minor_locator(mdates.HourLocator())
    ax.grid(True, which="major", color=GRID_MAJOR, linewidth=0.9)
    ax.grid(True, which="minor", color=GRID_MINOR, linewidth=0.6)

    for spine in ax.spines.values():
        spine.set_color(FRAME)
        spine.set_linewidth(1.2)

    ax.tick_params(axis="both", colors=TEXT_BODY, labelsize=9)
    ax.tick_params(axis="y", which="minor", length=0)
    ax.tick_params(axis="x", which="minor", length=4, color=FRAME)

    legend = [
        Line2D([0], [0], color=DEVICE_COLORS.get(d, TEXT_BODY), linewidth=1.6, label=d)
        for d, _ in series
    ]
    legend.append(
        Line2D([0], [0], color=TEXT_DIM, linewidth=1, linestyle=":",
               label=f"brew threshold {BREW_THRESHOLD:.0f} W")
    )
    fig.subplots_adjust(left=0.08, right=0.985, top=0.86, bottom=0.12)
    fig.legend(handles=legend, loc="lower center", ncol=len(legend), frameon=False,
               fontsize=9, bbox_to_anchor=(0.5, 0.055))
    fig.text(0.5, 0.02, "y-axis log · each device in its own color",
             ha="center", fontsize=8, color=TEXT_FOOT)

    fig.savefig(out_png, dpi=100)
    plt.close(fig)
    return out_png


if __name__ == "__main__":
    print(plot_power())