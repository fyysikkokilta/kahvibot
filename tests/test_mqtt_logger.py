import csv
import json
from types import SimpleNamespace

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
