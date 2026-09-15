"""Live wattage per coffee machine, straight off MQTT.

The plugs publish to `zigbee2mqtt/<device>` and the broker is already running on
this Pi, so the reader subscribes to it rather than reading anything off disk.
An earlier version tailed the power logger's CSV; that worked but was a log
being used as a channel, with up to a reporting interval of staleness and a
stat() on every tick. A subscription is push, costs nothing between messages,
and is the transport the data is already on.

Nothing here is required. With no broker, a wrong password, or paho absent, every
lookup returns None, which the filter reads as "regime unobserved" and falls back
to inferring whether a brew is happening. That is a real degradation, not a
silent wrong answer: the alternative, treating an unreachable plug as "not
brewing", would let the filter reject a genuine level rise.

The wattage matters because it names the regime. The element draws ~1450 W and
the hotplate 57-182 W (measured at the guild room), so a level rising while the
element is idle is the sensor changing its mind, not coffee appearing.
"""
from __future__ import annotations

import collections
import json
import logging
import threading
import time

log = logging.getLogger("kahvi.power")


class PowerBus:
    """Last reported watts per side, kept current by an MQTT subscription."""

    def __init__(self, host: str = "127.0.0.1", port: int = 1883, user: str = "",
                 password: str = "", base_topic: str = "zigbee2mqtt",
                 devices: dict | None = None, max_age_s: float = 900.0, clock=None,
                 history_s: float = 4 * 3600.0):
        self.host, self.port = host, int(port)
        self.user, self.password = user, password
        self.base_topic = base_topic.rstrip("/")
        self.devices = dict(devices or {})
        self.topics = {f"{self.base_topic}/{dev}": side for side, dev in self.devices.items()}
        self.max_age_s = float(max_age_s)
        self.clock = clock
        self._lock = threading.Lock()
        self._watts: dict = {}          # side -> (wall_seconds, watts)
        # Enough recent history for the graph's power strip, held in memory so
        # nothing has to read the logger's file to draw it. The plugs report on
        # change with a 5 min heartbeat, so a few hundred points covers hours.
        self.history_s = float(history_s)
        self._hist: dict = collections.defaultdict(lambda: collections.deque(maxlen=2000))
        self._client = None
        self.connected = False

    # -- lifecycle ---------------------------------------------------------
    def start(self) -> bool:
        """Connect and subscribe in a background thread. False if unavailable."""
        if not self.devices:
            return False
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            log.warning("paho-mqtt not installed; the filter runs without plug data")
            return False
        try:
            try:
                client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
            except AttributeError:                 # paho 1.x
                client = mqtt.Client()
            if self.user:
                client.username_pw_set(self.user, self.password)
            client.on_connect = self._on_connect
            client.on_message = self._on_message
            client.on_disconnect = self._on_disconnect
            client.connect_async(self.host, self.port, keepalive=60)
            client.loop_start()                    # paho owns the thread and reconnects
            self._client = client
            log.info("power bus: mqtt://%s:%d topics %s", self.host, self.port,
                     ", ".join(sorted(self.topics)))
            return True
        except Exception:  # noqa: BLE001 - the reader must start without the broker
            log.warning("power bus unavailable; the filter runs without plug data",
                        exc_info=True)
            return False

    def stop(self) -> None:
        if self._client is not None:
            try:
                self._client.loop_stop()
                self._client.disconnect()
            except Exception:  # noqa: BLE001
                pass

    # -- callbacks ---------------------------------------------------------
    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        code = getattr(reason_code, "value", reason_code)
        if code not in (0, None):
            log.warning("power bus connect refused: %s", reason_code)
            return
        self.connected = True
        for topic in self.topics:
            client.subscribe(topic)

    def _on_disconnect(self, client, userdata, *a, **kw):
        self.connected = False

    def _on_message(self, client, userdata, msg):
        side = self.topics.get(msg.topic)
        if side is None:
            return
        try:
            watts = float(json.loads(msg.payload).get("power"))
        except (ValueError, TypeError, AttributeError):
            return
        now = time.time()
        with self._lock:
            self._watts[side] = (now, watts)
            self._hist[side].append((now, watts))

    # -- reads -------------------------------------------------------------
    def watts(self, side: str):
        """Latest watts for this side, or None when unknown or stale.

        Stale counts as unknown on purpose: a plug that has dropped off the mesh
        must not be read as "definitely not brewing".
        """
        with self._lock:
            hit = self._watts.get(side)
        if hit is None:
            return None
        when, watts = hit
        if time.time() - when > self.max_age_s:
            return None
        return watts

    def history(self, side: str, since_wall: float | None = None):
        """(wall_seconds, watts) pairs for the graph, oldest first."""
        cutoff = (time.time() - self.history_s) if since_wall is None else since_wall
        with self._lock:
            return [(t, w) for t, w in self._hist.get(side, ()) if t >= cutoff]

    def state(self) -> dict:
        with self._lock:
            return {side: {"watts": w, "age_s": round(time.time() - t, 1)}
                    for side, (t, w) in self._watts.items()}
