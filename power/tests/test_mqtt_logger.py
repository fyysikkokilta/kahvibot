import csv
import json
from types import SimpleNamespace

import pandas as pd

import mqtt_logger


def test_csv_path_uses_data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(mqtt_logger, "DATA_DIR", tmp_path)
    assert mqtt_logger.csv_path("oikea") == tmp_path / "power_oikea.csv"


def test_ensure_csv_writes_header_once(tmp_path):
    path = tmp_path / "power_oikea.csv"
    mqtt_logger.ensure_csv(path)
    mqtt_logger.ensure_csv(path)  # should be idempotent, no duplicate header
    with open(path) as f:
        rows = list(csv.reader(f))
    assert rows == [["timestamp", "power"]]


def _msg(topic, payload):
    return SimpleNamespace(topic=topic, payload=payload)


def test_on_message_writes_row_for_known_topic(tmp_path, monkeypatch):
    monkeypatch.setattr(mqtt_logger, "DATA_DIR", tmp_path)
    topic = f"{mqtt_logger.MQTT_BASE_TOPIC}/oikea"
    msg = _msg(topic, json.dumps({"power": 42.5}).encode())

    mqtt_logger.on_message(None, None, msg)

    path = mqtt_logger.csv_path("oikea")
    with open(path) as f:
        rows = list(csv.reader(f))
    assert rows[0] == ["timestamp", "power"]
    assert rows[1][1] == "42.5"


def test_on_message_ignores_unknown_topic(tmp_path, monkeypatch):
    monkeypatch.setattr(mqtt_logger, "DATA_DIR", tmp_path)
    msg = _msg("zigbee2mqtt/../../etc/passwd", json.dumps({"power": 1}).encode())

    mqtt_logger.on_message(None, None, msg)

    assert list(tmp_path.iterdir()) == []


def test_on_message_ignores_invalid_json(tmp_path, monkeypatch):
    monkeypatch.setattr(mqtt_logger, "DATA_DIR", tmp_path)
    topic = f"{mqtt_logger.MQTT_BASE_TOPIC}/oikea"
    msg = _msg(topic, b"not json")

    mqtt_logger.on_message(None, None, msg)

    assert not mqtt_logger.csv_path("oikea").exists()


def test_on_message_ignores_missing_power(tmp_path, monkeypatch):
    monkeypatch.setattr(mqtt_logger, "DATA_DIR", tmp_path)
    topic = f"{mqtt_logger.MQTT_BASE_TOPIC}/oikea"
    msg = _msg(topic, json.dumps({"state": "ON"}).encode())

    mqtt_logger.on_message(None, None, msg)

    assert not mqtt_logger.csv_path("oikea").exists()


def test_on_message_ignores_non_numeric_power(tmp_path, monkeypatch):
    monkeypatch.setattr(mqtt_logger, "DATA_DIR", tmp_path)
    topic = f"{mqtt_logger.MQTT_BASE_TOPIC}/oikea"
    msg = _msg(topic, json.dumps({"power": "not-a-number"}).encode())

    mqtt_logger.on_message(None, None, msg)

    assert not mqtt_logger.csv_path("oikea").exists()


def test_on_message_writes_tz_aware_timestamp(tmp_path, monkeypatch):
    monkeypatch.setattr(mqtt_logger, "DATA_DIR", tmp_path)
    topic = f"{mqtt_logger.MQTT_BASE_TOPIC}/oikea"
    mqtt_logger.on_message(None, None, _msg(topic, json.dumps({"power": 7}).encode()))

    with open(mqtt_logger.csv_path("oikea")) as f:
        rows = list(csv.reader(f))
    assert rows[1][1] == "7.0"
    assert pd.to_datetime(rows[1][0]).tz is not None


def test_prune_csv_noop_when_under_limit(tmp_path):
    path = tmp_path / "power_oikea.csv"
    mqtt_logger.ensure_csv(path)
    mqtt_logger.prune_csv(path, keep=3)
    with open(path) as f:
        assert [r[0] for r in csv.reader(f)] == ["timestamp"]


def test_on_message_prunes_large_csv(tmp_path, monkeypatch):
    monkeypatch.setattr(mqtt_logger, "DATA_DIR", tmp_path)
    monkeypatch.setattr(mqtt_logger, "MAX_CSV_BYTES", 1)
    monkeypatch.setattr(mqtt_logger, "PRUNE_KEEP_ROWS", 3)
    topic = f"{mqtt_logger.MQTT_BASE_TOPIC}/oikea"
    for i in range(5):
        mqtt_logger.on_message(None, None, _msg(topic, json.dumps({"power": float(i)}).encode()))

    with open(mqtt_logger.csv_path("oikea")) as f:
        rows = list(csv.reader(f))
    assert rows[0] == ["timestamp", "power"]
    assert [r[1] for r in rows[1:]] == ["2.0", "3.0", "4.0"]


# --- streaming brew detection --------------------------------------------------


def test_brew_tracker_emits_start_and_end():
    from datetime import datetime, timedelta, timezone

    t0 = datetime(2026, 9, 10, 8, 0, tzinfo=timezone.utc)
    tr = mqtt_logger.BrewTracker(start_threshold=300, end_threshold=250)
    assert tr.update(t0, 90) is None                      # hotplate only
    start = tr.update(t0 + timedelta(seconds=10), 1400)
    assert start["event"] == "start"
    assert start["t"] == (t0 + timedelta(seconds=10)).isoformat()
    assert tr.update(t0 + timedelta(seconds=200), 1450) is None
    assert tr.update(t0 + timedelta(seconds=300), 260) is None   # still above the end threshold
    end = tr.update(t0 + timedelta(seconds=360), 95)
    assert end["event"] == "end"
    assert end["duration_s"] == 350.0
    assert end["peak_w"] == 1450
    assert tr.update(t0 + timedelta(seconds=400), 95) is None    # idle again


def test_on_message_appends_brew_events(tmp_path, monkeypatch):
    monkeypatch.setattr(mqtt_logger, "DATA_DIR", tmp_path)
    monkeypatch.setattr(mqtt_logger, "TRACKERS", {})
    topic = f"{mqtt_logger.MQTT_BASE_TOPIC}/oikea"
    for w in (5, 1400, 1400, 50, 5):
        mqtt_logger.on_message(None, None, _msg(topic, json.dumps({"power": w}).encode()))

    lines = mqtt_logger.brews_path("oikea").read_text().splitlines()
    events = [json.loads(line) for line in lines]
    assert [e["event"] for e in events] == ["start", "end"]
    assert events[1]["peak_w"] == 1400.0
    assert pd.to_datetime(events[1]["end"]).tz is not None
