"""systemd readiness and watchdog for the reader daemon.

Why a watchdog at all: on 2026-09-15 this service spun at 56 % of a core in
userspace for 21 h -- readings frozen at the 21:06:36 tick, the loop thread
never executing queued IPC requests -- while systemd reported it `active
(running)` the whole time. `Restart=always` cannot help, because the process
never exited. A watchdog is the only supervision that catches a live process
that has stopped doing its job.

What counts as "doing its job" is deliberately *not* "the process is running":
that is precisely what systemd already believed. It is a tick completing, at
roughly the configured cadence -- neither stalled nor running away. Both shapes
are checked because both have been seen: the 09-15 wedge stalled (no tick
completed at all), while a cadence that collapses to zero would spin through
`run_due` producing nothing. Ticks are counted rather than readings, so a
genuinely busy camera -- the bot holding the flock, which is normal and
self-clearing -- is not mistaken for a hang.
"""
from __future__ import annotations

import logging
import os
import socket
from typing import Optional

log = logging.getLogger("kahvi.notify")


class SystemdNotifier:
    """sd_notify without the systemd bindings: one datagram to $NOTIFY_SOCKET.

    Silent no-op when the variable is absent, so the daemon runs identically
    under the gym, a shell, or `python run_daemon.py` on a dev box.
    """

    def __init__(self, env=None, sock_factory=None):
        env = os.environ if env is None else env
        self.addr = env.get("NOTIFY_SOCKET", "")
        # An @-prefixed path is the abstract namespace, which is a NUL byte.
        if self.addr.startswith("@"):
            self.addr = "\0" + self.addr[1:]
        self._sock_factory = sock_factory or (
            lambda: socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM))
        self.watchdog_usec = 0
        try:
            self.watchdog_usec = int(env.get("WATCHDOG_USEC", "0"))
        except (TypeError, ValueError):
            pass

    @property
    def enabled(self) -> bool:
        return bool(self.addr)

    @property
    def ping_interval(self) -> float:
        """Half the deadline, the conventional margin; 10 s if unset."""
        return (self.watchdog_usec / 2e6) if self.watchdog_usec > 0 else 10.0

    def notify(self, msg: str) -> bool:
        if not self.addr:
            return False
        try:
            s = self._sock_factory()
            try:
                s.sendto(msg.encode("ascii"), self.addr)
            finally:
                s.close()
            return True
        except OSError:
            return False

    def ready(self) -> bool:
        return self.notify("READY=1")

    def watchdog(self) -> bool:
        return self.notify("WATCHDOG=1")

    def status(self, text: str) -> bool:
        return self.notify("STATUS=%s" % text)


class LoopHealth:
    """Is the service loop still doing its job? Pure arithmetic, so it tests.

    `check` returns None when healthy, otherwise the reason to withhold the
    ping -- which the journal prints, so a watchdog kill explains itself
    instead of looking like a second mystery.
    """

    def __init__(self, stall_floor: float = 60.0, stall_factor: float = 4.0,
                 runaway_factor: float = 5.0, rate_window: float = 5.0):
        self.stall_floor = float(stall_floor)
        self.stall_factor = float(stall_factor)
        self.runaway_factor = float(runaway_factor)
        self.rate_window = float(rate_window)
        self._prev: Optional[tuple] = None      # (mono, ticks)

    def stall_after(self, cadence: float) -> float:
        return max(self.stall_floor, float(cadence) * self.stall_factor)

    def check(self, now: float, last_tick_mono: float, ticks: int,
              cadence: float) -> Optional[str]:
        limit = self.stall_after(cadence)
        idle = now - last_tick_mono
        if idle > limit:
            return "no tick completed in %.0f s (cadence %.0f s, limit %.0f s)" % (
                idle, cadence, limit)

        prev = self._prev
        if prev is None:
            self._prev = (now, ticks)
            return None
        elapsed = now - prev[0]
        if elapsed >= self.rate_window:
            self._prev = (now, ticks)
            rate = (ticks - prev[1]) / elapsed if elapsed > 0 else 0.0
            expected = 1.0 / cadence if cadence > 0 else float("inf")
            if cadence > 0 and rate > self.runaway_factor * expected:
                return "tick rate %.1f/s against an expected %.2f/s (cadence %.0f s)" % (
                    rate, expected, cadence)
        return None
