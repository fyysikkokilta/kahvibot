"""Clocks. The service never calls time.* directly, so the gym can run a day in
seconds while charging Pi-scaled compute costs to a virtual clock."""
from __future__ import annotations

import time


class RealClock:
    scale = 1.0

    def wall(self) -> float:
        return time.time()

    def mono(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        if seconds > 0:
            time.sleep(seconds)

    def charge(self, local_seconds: float) -> float:
        """Compute already happened in real time; nothing to add."""
        return 0.0


class VirtualClock:
    """Manually advanced clock. `charge()` converts measured local compute time
    into virtual seconds via `scale` (e.g. Pi-3B seconds per desktop second)."""

    def __init__(self, start_wall: float, scale: float = 1.0):
        self._wall = float(start_wall)
        self._mono = 0.0
        self.scale = float(scale)
        self.charged = 0.0          # virtual seconds of compute charged so far
        self.slept = 0.0

    def wall(self) -> float:
        return self._wall

    def mono(self) -> float:
        return self._mono

    def advance(self, seconds: float) -> None:
        if seconds > 0:
            self._wall += seconds
            self._mono += seconds

    def sleep(self, seconds: float) -> None:
        self.slept += max(0.0, seconds)
        self.advance(seconds)

    def charge(self, local_seconds: float) -> float:
        v = max(0.0, local_seconds) * self.scale
        self.charged += v
        self.advance(v)
        return v

    def set_wall(self, wall: float) -> None:
        """Jump forward (never back) to an absolute wall time."""
        if wall > self._wall:
            self.advance(wall - self._wall)
