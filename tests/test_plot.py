import csv
from datetime import datetime, timedelta

import pandas as pd
import pytest

import plot


def write_csv(path, rows):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["timestamp", "power"])
        for ts, power in rows:
            w.writerow([ts, power])


def iso(dt):
    return dt.isoformat()


# --- get_csv_path -----------------------------------------------------------


def test_get_csv_path_builds_expected_filename():
    path = plot.get_csv_path("oikea")
    assert path.name == "power_oikea.csv"
    assert path.parent == plot.DATA_DIR


@pytest.mark.parametrize(
    "device",
    ["../etc/passwd", "oikea/../../secret", "oikea; rm -rf", "a b", ""],
)
def test_get_csv_path_rejects_unsafe_device_names(device):
    with pytest.raises(ValueError):
        plot.get_csv_path(device)


# --- fmt_duration ------------------------------------------------------------


@pytest.mark.parametrize(
    "seconds,expected",
    [
        (5, "5s"),
        (65, "1m 05s"),
        (3665, "1h 01m"),
        (-1, ""),
    ],
)
def test_fmt_duration(seconds, expected):
    assert plot.fmt_duration(timedelta(seconds=seconds)) == expected


# --- brew_summary ------------------------------------------------------------


def test_estimate_cups_returns_none_without_calibration(monkeypatch):
    monkeypatch.setattr(plot, "CUP_CALIBRATION", [])
    assert plot.estimate_cups(timedelta(seconds=300)) is None


def test_estimate_cups_single_point_scales_linearly(monkeypatch):
    monkeypatch.setattr(plot, "CUP_CALIBRATION", [(400.0, 8.0)])
    assert plot.estimate_cups(timedelta(seconds=200)) == pytest.approx(4.0)
    assert plot.estimate_cups(timedelta(seconds=400)) == pytest.approx(8.0)


def test_estimate_cups_two_points_fits_line_with_offset(monkeypatch):
    # 100s of fixed warm-up + 50s/cup: 6 cups -> 400s, 4 cups -> 300s
    monkeypatch.setattr(plot, "CUP_CALIBRATION", [(400.0, 6.0), (300.0, 4.0)])
    assert plot.estimate_cups(timedelta(seconds=350)) == pytest.approx(5.0)
    assert plot.estimate_cups(timedelta(seconds=200)) == pytest.approx(2.0)


def test_estimate_cups_never_returns_negative(monkeypatch):
    monkeypatch.setattr(plot, "CUP_CALIBRATION", [(400.0, 6.0), (300.0, 4.0)])
    assert plot.estimate_cups(timedelta(seconds=0)) == pytest.approx(0.0)


def test_brew_summary_no_brew():
    text = plot.brew_summary(None)
    assert "No brews detected" in text
    assert f"{plot.BREW_THRESHOLD:.0f}" in text


def test_brew_summary_ongoing_brew():
    now = pd.Timestamp.now()
    brew = {
        "start": now - pd.Timedelta(minutes=1),
        "end": now - pd.Timedelta(seconds=30),
        "peak": 950.0,
        "duration": pd.Timedelta(seconds=30),
    }
    text = plot.brew_summary(brew, now=now)
    assert "brewing right now" in text
    assert "950 W" in text


def test_brew_summary_past_brew():
    now = pd.Timestamp.now()
    brew = {
        "start": now - pd.Timedelta(hours=2),
        "end": now - pd.Timedelta(hours=1, minutes=59),
        "peak": 800.0,
        "duration": pd.Timedelta(seconds=45),
    }
    text = plot.brew_summary(brew, now=now)
    assert "ago" in text
    assert "brewing right now" not in text


def test_brew_summary_omits_cups_without_calibration(monkeypatch):
    monkeypatch.setattr(plot, "CUP_CALIBRATION", [])
    now = pd.Timestamp.now()
    brew = {
        "start": now - pd.Timedelta(seconds=400),
        "end": now,
        "peak": 900.0,
        "duration": pd.Timedelta(seconds=400),
    }
    assert "cups" not in plot.brew_summary(brew, now=now)


def test_brew_summary_includes_cups_with_calibration(monkeypatch):
    monkeypatch.setattr(plot, "CUP_CALIBRATION", [(400.0, 8.0)])
    now = pd.Timestamp.now()
    brew = {
        "start": now - pd.Timedelta(seconds=400),
        "end": now,
        "peak": 900.0,
        "duration": pd.Timedelta(seconds=400),
    }
    assert "~8.0 cups" in plot.brew_summary(brew, now=now)


# --- detect_brews / _hysteresis_events ---------------------------------------


def test_detect_brews_no_file_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(plot, "DATA_DIR", tmp_path)
    assert plot.detect_brews("oikea") == []


def test_detect_brews_finds_completed_brew(tmp_path, monkeypatch):
    monkeypatch.setattr(plot, "DATA_DIR", tmp_path)
    base = datetime(2026, 1, 1, 10, 0, 0)
    rows = [
        (iso(base), 10),
        (iso(base + timedelta(seconds=10)), 400),  # brew starts
        (iso(base + timedelta(seconds=20)), 900),  # peak
        (iso(base + timedelta(seconds=30)), 50),  # brew ends (below HEAT)
        (iso(base + timedelta(seconds=40)), 10),
    ]
    write_csv(plot.get_csv_path("oikea"), rows)

    brews = plot.detect_brews("oikea")
    assert len(brews) == 1
    brew = brews[0]
    assert brew["peak"] == 900
    assert brew["duration"] == timedelta(seconds=20)


def test_detect_brews_ongoing_brew_still_reported(tmp_path, monkeypatch):
    monkeypatch.setattr(plot, "DATA_DIR", tmp_path)
    base = datetime(2026, 1, 1, 10, 0, 0)
    rows = [
        (iso(base), 10),
        (iso(base + timedelta(seconds=10)), 400),
        (iso(base + timedelta(seconds=20)), 900),
    ]
    write_csv(plot.get_csv_path("oikea"), rows)

    brews = plot.detect_brews("oikea")
    assert len(brews) == 1
    assert brews[0]["peak"] == 900


def test_detect_brews_ignores_rows_with_bad_timestamps(tmp_path, monkeypatch):
    monkeypatch.setattr(plot, "DATA_DIR", tmp_path)
    base = datetime(2026, 1, 1, 10, 0, 0)
    rows = [
        ("not-a-timestamp", 400),
        (iso(base), 400),
        (iso(base + timedelta(seconds=10)), 50),
    ]
    write_csv(plot.get_csv_path("oikea"), rows)

    # Should not raise despite the malformed row.
    brews = plot.detect_brews("oikea")
    assert len(brews) == 1


def test_last_brew_returns_none_when_no_brews(tmp_path, monkeypatch):
    monkeypatch.setattr(plot, "DATA_DIR", tmp_path)
    base = datetime(2026, 1, 1, 10, 0, 0)
    rows = [(iso(base), 10), (iso(base + timedelta(seconds=10)), 20)]
    write_csv(plot.get_csv_path("oikea"), rows)
    assert plot.last_brew("oikea") is None


# --- plot_power ---------------------------------------------------------------


def test_plot_power_raises_when_no_file(tmp_path, monkeypatch):
    monkeypatch.setattr(plot, "DATA_DIR", tmp_path)
    with pytest.raises(FileNotFoundError):
        plot.plot_power("oikea")


def test_plot_power_raises_when_all_data_too_old(tmp_path, monkeypatch):
    monkeypatch.setattr(plot, "DATA_DIR", tmp_path)
    old = datetime.now() - timedelta(days=10)
    write_csv(plot.get_csv_path("oikea"), [(iso(old), 100)])
    with pytest.raises(FileNotFoundError):
        plot.plot_power("oikea", hours=24)


def test_plot_power_writes_png_and_survives_bad_rows(tmp_path, monkeypatch):
    monkeypatch.setattr(plot, "DATA_DIR", tmp_path)
    now = datetime.now()
    rows = [
        (iso(now - timedelta(minutes=5)), "not-a-number"),  # corrupt row
        (iso(now - timedelta(minutes=1)), 123),
    ]
    write_csv(plot.get_csv_path("oikea"), rows)

    out_png = tmp_path / "out.png"
    result = plot.plot_power("oikea", out_png=out_png, hours=24)
    assert result == out_png
    assert out_png.is_file()
