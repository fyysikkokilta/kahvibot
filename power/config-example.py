import os
from pathlib import Path

# Copy this file to config.py and fill in your real values:
#   cp config-example.py config.py

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)


def _env(name, default):
    return os.environ.get(name, default)


MQTT_BROKER = _env("MQTT_BROKER", "localhost")
MQTT_PORT = int(_env("MQTT_PORT", "1883"))
MQTT_USER = _env("MQTT_USER", "zigbee2mqtt")
MQTT_PASS = _env("MQTT_PASS", "CHANGE_ME")

DEVICES = _env("DEVICES", "vasen,oikea").split(",")
MQTT_BASE_TOPIC = _env("MQTT_BASE_TOPIC", "zigbee2mqtt")
DEFAULT_DEVICE = _env("DEFAULT_DEVICE", "oikea")

# A brew starts when power rises above BREW_THRESHOLD (the heating element
# draws ~1.4 kW) and ends when it falls below HEAT. HEAT must sit clearly above
# the hotplate's own draw (~100 W on a Moccamaster): with the plate cycling
# around the threshold one brew splits into several and the durations that feed
# the cup estimate become garbage. Plot the CSV before lowering this.
BREW_THRESHOLD = float(_env("BREW_THRESHOLD", "300"))
HEAT = float(_env("HEAT", "250"))


def _parse_calibration(raw):
    points = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        secs, cups = part.split(":")
        points.append((float(secs), float(cups)))
    return points


# Reference brews for estimating cup count from brew duration, as
# "seconds:cups" pairs, e.g. "400:8,300:6". The Moccamaster draws roughly
# constant power for as long as water is still passing through the filter, so
# brew duration scales with the amount of water. One point assumes brewing
# starts flowing water immediately (no fixed offset); two or more points are
# fit with a line. Leave empty until you have measurements.
CUP_CALIBRATION = _parse_calibration(_env("CUP_CALIBRATION", ""))
