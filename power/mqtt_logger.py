import json
import csv
import logging
import signal
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

from config import (
    BREW_THRESHOLD,
    HEAT,
    MQTT_BROKER,
    MQTT_PORT,
    MQTT_USER,
    MQTT_PASS,
    MQTT_BASE_TOPIC,
    DEVICES,
    DATA_DIR,
)

logger = logging.getLogger("mqtt_logger")

DEVICES_BY_TOPIC = {f"{MQTT_BASE_TOPIC}/{name}": name for name in DEVICES}

# Bound CSV growth: once a file exceeds this many bytes it is rewritten to keep
# only the newest PRUNE_KEEP_ROWS samples, so full-file reads by plot.py stay
# bounded no matter how long the log has been running.
MAX_CSV_BYTES = 8 * 1024 * 1024
PRUNE_KEEP_ROWS = 150_000


def csv_path(device):
    return DATA_DIR / f"power_{device}.csv"


def brews_path(device):
    return DATA_DIR / f"brews_{device}.jsonl"


class BrewTracker:
    """Streaming twin of plot._hysteresis_events: a brew starts when power rises
    above start_threshold and ends when it falls below end_threshold. update()
    returns an event dict at those two moments and None otherwise, so brews are
    recorded as they happen instead of being re-derived from the whole CSV on
    every request."""

    def __init__(self, start_threshold=BREW_THRESHOLD, end_threshold=HEAT):
        self.start_threshold = float(start_threshold)
        self.end_threshold = float(end_threshold)
        self.start = None
        self.peak = 0.0

    def update(self, ts, power):
        power = float(power)
        if self.start is None:
            if power > self.start_threshold:
                self.start, self.peak = ts, power
                return {"event": "start", "t": ts.isoformat(), "power": power}
            return None
        self.peak = max(self.peak, power)
        if power < self.end_threshold:
            ev = {"event": "end", "start": self.start.isoformat(), "end": ts.isoformat(),
                  "duration_s": round((ts - self.start).total_seconds(), 1), "peak_w": self.peak}
            self.start, self.peak = None, 0.0
            return ev
        return None


def append_event(path, event):
    """One JSON object per line. Never pruned: a few lines per brew is the
    machine's whole history, and kahvibot reads the last line for its caption."""
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")


TRACKERS = {name: BrewTracker() for name in DEVICES}


def ensure_csv(path):
    # Single open: append mode with tell()==0 detects an empty file, so there
    # is no separate exists() check racing with another writer (TOCTOU).
    with open(path, "a", newline="") as f:
        if f.tell() == 0:
            csv.writer(f).writerow(["timestamp", "power"])


def append_row(path, ts, power):
    with open(path, "a", newline="") as f:
        writer = csv.writer(f)
        if f.tell() == 0:
            writer.writerow(["timestamp", "power"])
        writer.writerow([ts, power])


def prune_csv(path, keep=None):
    if keep is None:
        keep = PRUNE_KEEP_ROWS
    with open(path, newline="") as f:
        header = f.readline()
        lines = f.readlines()
    if len(lines) <= keep:
        return
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", newline="") as f:
        f.write(header)
        f.writelines(lines[-keep:])
    tmp.replace(path)


def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code != 0:
        logger.error("MQTT connect failed: %s", reason_code)
        return
    for topic in DEVICES_BY_TOPIC:
        client.subscribe(topic)
        logger.info("Subscribed: %s", topic)


def on_message(client, userdata, msg):
    dev_name = DEVICES_BY_TOPIC.get(msg.topic)
    if dev_name is None:
        return
    try:
        payload = json.loads(msg.payload)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return
    try:
        power = float(payload.get("power"))
    except (TypeError, ValueError):
        return
    now = datetime.now(timezone.utc)
    ts = now.isoformat()
    path = csv_path(dev_name)
    append_row(path, ts, power)
    event = TRACKERS.setdefault(dev_name, BrewTracker()).update(now, power)
    if event is not None:
        append_event(brews_path(dev_name), event)
        logger.info("[%s] %s: brew %s", ts, dev_name, event["event"])
    if path.stat().st_size > MAX_CSV_BYTES:
        prune_csv(path)
    logger.info("[%s] %s: %s W", ts, dev_name, power)


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.username_pw_set(MQTT_USER, MQTT_PASS)
    client.on_connect = on_connect
    client.on_message = on_message

    for name in DEVICES:
        ensure_csv(csv_path(name))

    def stop(signum, frame):
        logger.info("Disconnecting from MQTT...")
        client.disconnect()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    logger.info("Connecting to MQTT at %s:%s ...", MQTT_BROKER, MQTT_PORT)
    client.connect_async(MQTT_BROKER, MQTT_PORT, keepalive=60)
    try:
        client.loop_forever()
    except KeyboardInterrupt:
        stop(signal.SIGINT, None)
    logger.info("Bye.")


if __name__ == "__main__":
    main()