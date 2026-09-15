"""Latest wattage per coffee machine, read from the power logger's CSV.

The plugs publish over MQTT and `power/mqtt_logger.py` appends every sample to
`data/power_<device>.csv`. The reader service only needs the most recent value,
so it tails that file rather than holding a second MQTT subscription: one
subscriber, one writer, and the reader keeps working when the broker restarts.

The wattage matters because it says which regime the machine is in. The element
draws ~1450 W and the hotplate 57-182 W (measured at the guild room), so a level
that rises while the element is off is the sensor changing its mind, not coffee
appearing.
"""
from __future__ import annotations

import os
from pathlib import Path


class PowerTail:
    """Last reported watts per side, cached briefly so a tick costs one stat()."""

    def __init__(self, directory: str | os.PathLike, devices: dict, max_age_s: float = 600.0,
                 cache_s: float = 5.0, clock=None):
        self.dir = Path(directory) if directory else None
        self.devices = dict(devices or {})
        self.max_age_s = float(max_age_s)
        self.cache_s = float(cache_s)
        self.clock = clock
        self._cache: dict = {}          # side -> (mono_when_read, watts|None)

    def _now(self) -> float:
        if self.clock is not None:
            return self.clock.mono()
        import time
        return time.monotonic()

    def _read_tail(self, path: Path, tail_bytes: int = 4096):
        try:
            size = os.path.getsize(path)
            with open(path, "rb") as fh:
                if size > tail_bytes:
                    fh.seek(size - tail_bytes)
                    fh.readline()
                lines = [ln for ln in fh.read().decode("utf-8", "replace").splitlines() if ln.strip()]
        except OSError:
            return None, None
        for line in reversed(lines):
            parts = line.rsplit(",", 1)
            if len(parts) != 2:
                continue
            try:
                return parts[0], float(parts[1])
            except ValueError:
                continue
        return None, None

    def watts(self, side: str):
        """Latest watts for this side, or None when unknown.

        None is meaningful: it tells the filter the regime is unobserved, and it
        falls back to inferring brewing rather than assuming the machine is idle.
        A stale file counts as unknown for the same reason - a plug that dropped
        off the mesh must not be read as "definitely not brewing".
        """
        if self.dir is None or side not in self.devices:
            return None
        now = self._now()
        hit = self._cache.get(side)
        if hit is not None and now - hit[0] < self.cache_s:
            return hit[1]
        stamp, watts = self._read_tail(self.dir / f"power_{self.devices[side]}.csv")
        if watts is not None and stamp is not None:
            try:
                from datetime import datetime, timezone
                age = (datetime.now(timezone.utc) - datetime.fromisoformat(stamp)).total_seconds()
                if age > self.max_age_s:
                    watts = None
            except ValueError:
                watts = None
        self._cache[side] = (now, watts)
        return watts
