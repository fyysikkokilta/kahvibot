import paho.mqtt.client as mqtt
import json
import csv
import signal
from datetime import datetime

from config import (
    MQTT_BROKER,
    MQTT_PORT,
    MQTT_USER,
    MQTT_PASS,
    MQTT_BASE_TOPIC,
    DEVICES,
    DATA_DIR,
)

DEVICES_BY_TOPIC = {f"{MQTT_BASE_TOPIC}/{name}": name for name in DEVICES}


def csv_path(device):
    return DATA_DIR / f"power_{device}.csv"


def ensure_csv(path):
    write_header = not path.exists()
    with open(path, "a", newline="") as f:
        if write_header:
            csv.writer(f).writerow(["timestamp", "power"])


def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code != 0:
        print(f"MQTT connect failed: {reason_code}")
        return
    for topic in DEVICES_BY_TOPIC:
        client.subscribe(topic)
        print(f"Subscribed: {topic}")


def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return
    power = payload.get("power")
    if power is None:
        return
    dev_name = DEVICES_BY_TOPIC.get(msg.topic, msg.topic.split("/")[-1])
    path = csv_path(dev_name)
    ensure_csv(path)
    ts = datetime.now().isoformat()
    with open(path, "a", newline="") as f:
        csv.writer(f).writerow([ts, power])
    print(f"[{ts}] {dev_name}: {power} W")


def main():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.username_pw_set(MQTT_USER, MQTT_PASS)
    client.on_connect = on_connect
    client.on_message = on_message

    for name in DEVICES:
        ensure_csv(csv_path(name))

    def stop(signum, frame):
        print("\nDisconnecting from MQTT...")
        client.disconnect()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    print("Connecting to MQTT...")
    client.connect_async(MQTT_BROKER, MQTT_PORT, keepalive=60)
    try:
        client.loop_forever()
    except KeyboardInterrupt:
        stop(signal.SIGINT, None)
    print("Bye.")


if __name__ == "__main__":
    main()