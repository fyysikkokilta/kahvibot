"""The systemd watchdog: sd_notify plumbing and the liveness rule.

Pure arithmetic and a fake datagram socket, so this runs anywhere -- no
systemd, no model, no camera. The cases are the ones the field produced:
the 2026-09-15 stall, a night cadence that must not look like one, and a
runaway loop.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.notify import LoopHealth, SystemdNotifier  # noqa: E402


class FakeSock:
    """Captures sendto() instead of touching the kernel."""

    sent: list = []

    def __init__(self):
        FakeSock.sent = getattr(FakeSock, "sent", [])

    def sendto(self, data, addr):
        FakeSock.sent.append((data, addr))

    def close(self):
        pass


# -- SystemdNotifier ---------------------------------------------------------

def test_disabled_without_notify_socket():
    n = SystemdNotifier(env={})
    assert not n.enabled
    assert n.ready() is False          # a no-op, not a crash
    assert n.watchdog() is False


def test_sends_ready_and_watchdog():
    FakeSock.sent = []
    n = SystemdNotifier(env={"NOTIFY_SOCKET": "/run/systemd/notify"},
                        sock_factory=FakeSock)
    assert n.enabled
    assert n.ready() is True
    assert n.watchdog() is True
    assert FakeSock.sent == [(b"READY=1", "/run/systemd/notify"),
                             (b"WATCHDOG=1", "/run/systemd/notify")]


def test_abstract_namespace_address():
    """An @-prefixed NOTIFY_SOCKET is the abstract namespace: a leading NUL."""
    FakeSock.sent = []
    n = SystemdNotifier(env={"NOTIFY_SOCKET": "@/org/fdo/x"}, sock_factory=FakeSock)
    n.ready()
    assert FakeSock.sent[0][1] == "\0/org/fdo/x"


def test_ping_interval_is_half_the_deadline():
    n = SystemdNotifier(env={"NOTIFY_SOCKET": "/x", "WATCHDOG_USEC": "120000000"})
    assert n.ping_interval == 60.0
    assert SystemdNotifier(env={"NOTIFY_SOCKET": "/x"}).ping_interval == 10.0
    # a malformed value must not take the daemon down
    assert SystemdNotifier(env={"NOTIFY_SOCKET": "/x",
                                "WATCHDOG_USEC": "nonsense"}).ping_interval == 10.0


def test_send_failure_is_swallowed():
    class Exploding(FakeSock):
        def sendto(self, data, addr):
            raise OSError("no such socket")

    n = SystemdNotifier(env={"NOTIFY_SOCKET": "/x"}, sock_factory=Exploding)
    assert n.watchdog() is False       # reported, never raised


# -- LoopHealth --------------------------------------------------------------

def test_healthy_loop_pings():
    h = LoopHealth()
    assert h.check(now=100.0, last_tick_mono=95.0, ticks=10, cadence=10.0) is None


def test_stall_is_caught():
    """2026-09-15: the process stayed alive, the loop stopped completing ticks."""
    h = LoopHealth()
    assert h.check(now=100.0, last_tick_mono=99.0, ticks=10, cadence=10.0) is None
    # limit at cadence 10 s is max(60, 40) = 60 s
    assert h.check(now=158.0, last_tick_mono=99.0, ticks=10, cadence=10.0) is None
    reason = h.check(now=170.0, last_tick_mono=99.0, ticks=10, cadence=10.0)
    assert reason is not None and "no tick completed" in reason


def test_night_cadence_is_not_a_stall():
    """Dark backs off to 60 s; a 90 s gap is normal, not a hang."""
    h = LoopHealth()
    assert h.stall_after(60.0) == 240.0
    assert h.check(now=1000.0, last_tick_mono=910.0, ticks=5, cadence=60.0) is None


def test_busy_camera_is_not_a_stall():
    """A tick that returns early (bot holds the camera flock) still counts."""
    h = LoopHealth()
    assert h.check(now=500.0, last_tick_mono=495.0, ticks=400, cadence=10.0) is None


def test_runaway_is_caught():
    """A cadence that collapses spins run_due without producing anything."""
    h = LoopHealth()
    assert h.check(now=0.0, last_tick_mono=0.0, ticks=0, cadence=10.0) is None
    # 6 s later, 600 ticks: 100/s against an expected 0.1/s
    reason = h.check(now=6.0, last_tick_mono=6.0, ticks=600, cadence=10.0)
    assert reason is not None and "tick rate" in reason


def test_rate_window_ignores_short_samples():
    """Sub-window gaps carry no rate signal and must not false-fire."""
    h = LoopHealth()
    assert h.check(now=0.0, last_tick_mono=0.0, ticks=0, cadence=10.0) is None
    assert h.check(now=0.5, last_tick_mono=0.5, ticks=50, cadence=10.0) is None


def test_recovers_after_a_stall():
    h = LoopHealth()
    h.check(now=200.0, last_tick_mono=100.0, ticks=10, cadence=10.0)
    assert h.check(now=210.0, last_tick_mono=209.0, ticks=11, cadence=10.0) is None
