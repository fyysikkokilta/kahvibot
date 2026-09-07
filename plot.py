import re

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import pandas as pd

from config import (
    DATA_DIR,
    DEFAULT_DEVICE,
    BREW_THRESHOLD,
    HEAT,
    PLOT_HOURS,
    CUP_CALIBRATION,
)

_DEVICE_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def get_csv_path(device=DEFAULT_DEVICE):
    if not _DEVICE_RE.match(device):
        raise ValueError(f"Invalid device name: {device!r}")
    return DATA_DIR / f"power_{device}.csv"


def _hysteresis_events(df, start_threshold, end_threshold):
    events = []
    in_brew = False
    start_pos = None
    peak = 0.0
    for pos, row in df.iterrows():
        p = float(row["power"])
        if not in_brew:
            if p > start_threshold:
                in_brew = True
                start_pos = pos
                peak = p
        else:
            peak = max(peak, p)
            if p < end_threshold:
                events.append(
                    {
                        "start": df.loc[start_pos, "timestamp"],
                        "end": row["timestamp"],
                        "peak": peak,
                        "duration": row["timestamp"] - df.loc[start_pos, "timestamp"],
                    }
                )
                in_brew = False
    if in_brew:
        last = df.iloc[-1]
        events.append(
            {
                "start": df.loc[start_pos, "timestamp"],
                "end": last["timestamp"],
                "peak": peak,
                "duration": last["timestamp"] - df.loc[start_pos, "timestamp"],
            }
        )
    return events


def detect_brews(device=DEFAULT_DEVICE, start_threshold=BREW_THRESHOLD, end_threshold=HEAT):
    csv_path = get_csv_path(device)
    if not csv_path.is_file():
        return []
    df = pd.read_csv(csv_path)
    if df.empty or "power" not in df.columns:
        return []
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
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
    if not CUP_CALIBRATION:
        return None
    seconds = duration.total_seconds() if hasattr(duration, "total_seconds") else duration
    points = sorted(CUP_CALIBRATION)
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
    start, end = brew["start"], brew["end"]
    ongoing = end >= now - pd.Timedelta(seconds=90)
    when = "brewing right now" if ongoing else f"{fmt_duration(now - end)} ago"
    cups = estimate_cups(brew["duration"])
    cups_str = f" · ~{cups:.1f} cups" if cups is not None else ""
    return (
        f"☕ Last brew: {when}\n"
        f"   {start.strftime('%H:%M')}–{end.strftime('%H:%M')} · "
        f"{fmt_duration(brew['duration'])} · peak {brew['peak']:.0f} W{cups_str}"
    )


def plot_power(device=DEFAULT_DEVICE, out_png=None, hours=PLOT_HOURS):
    csv_path = get_csv_path(device)
    if not csv_path.is_file():
        raise FileNotFoundError(f"No data for {device}")
    df = pd.read_csv(csv_path)
    if df.empty or "timestamp" not in df.columns or "power" not in df.columns:
        raise FileNotFoundError(f"No data for {device}")
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df["power"] = pd.to_numeric(df["power"], errors="coerce")
    df = df.dropna(subset=["timestamp", "power"])
    df = df[df["timestamp"] >= pd.Timestamp.now() - pd.Timedelta(hours=hours)]
    if df.empty:
        raise FileNotFoundError(f"No data for {device} in the last {hours:g} h")
    y = df["power"].clip(lower=1.0)

    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(df["timestamp"], y, linewidth=0.8)
    ax.set_yscale("log")
    ax.set_xlabel("Time")
    ax.set_ylabel("Power (W, log)")
    ax.set_title(f"{device} — Power Usage (last {hours:g} h)")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    fig.autofmt_xdate()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()

    if out_png is None:
        out_png = DATA_DIR / f"plot_{device}.png"
    fig.savefig(out_png, dpi=120)
    plt.close(fig)
    return out_png


if __name__ == "__main__":
    print(plot_power())