"""The SQLite store, the power bus writing into it, and the import/export CLI."""
from __future__ import annotations

import io
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline import kahvidb                                  # noqa: E402
from pipeline.clock import VirtualClock                       # noqa: E402
from pipeline.graphing import DayBuffer                       # noqa: E402
from pipeline.power import BrewTracker, PowerBus              # noqa: E402
from pipeline.rbpf import Calibration, PotRBPF                # noqa: E402
from pipeline.store import ReadingsStore, connect, iso_utc, last_brew, last_reading_t  # noqa: E402

T0 = 1_800_000_000.0


def _store(flush_sec=60.0):
    tmp = Path(tempfile.mkdtemp())
    clock = VirtualClock(T0)
    return ReadingsStore(tmp / "kahvi.db", clock, flush_sec=flush_sec), clock, tmp


def _rec(wall, seq, ml=400.0):
    return {"t": iso_utc(wall), "seq": seq, "src": "sampler", "luma": 90.0,
            "pots": [{"s": "left", "h": 0.3, "e": 0.5, "d": 0.9, "ml": ml}]}


def test_readings_are_batched_until_the_flush_interval():
    store, clock, tmp = _store()
    store.add(_rec(T0, 0), usable=True)
    assert not store.flush()                          # interval not reached
    ro = connect(tmp / "kahvi.db", readonly=True)
    assert last_reading_t(ro) is None
    clock.advance(61)
    assert store.flush()
    assert last_reading_t(ro) == T0
    assert store.latest["last_usable_seq"] == 0


def test_brew_event_forces_the_next_flush():
    store, clock, tmp = _store()
    store.add_brew("west", {"event": "start", "start": T0, "peak_w": 1450.0})
    assert store.flush()                              # urgent: no interval wait
    ro = connect(tmp / "kahvi.db", readonly=True)
    assert last_brew(ro, "west") == (T0, None)       # running
    store.add_brew("west", {"event": "end", "start": T0, "end": T0 + 240,
                             "duration_s": 240.0, "peak_w": 1500.0})
    store.flush()
    assert last_brew(ro, "west") == (T0, T0 + 240)


def test_brew_tracker_hysteresis():
    tr = BrewTracker(start_w=300, end_w=250)
    assert tr.update(0, 80) is None
    assert tr.update(10, 1450)["event"] == "start"
    assert tr.update(20, 270) is None                 # between the thresholds: still brewing
    ev = tr.update(250, 82)
    assert ev == {"event": "end", "start": 10, "end": 250, "duration_s": 240.0, "peak_w": 1450.0}


def test_power_bus_logs_messages_and_brews_into_the_store():
    store, clock, tmp = _store()
    bus = PowerBus(devices={"left": "west"}, sink=store)
    for w in (80.0, 1450.0, 1460.0, 82.0):
        bus._on_message(None, None, SimpleNamespace(topic="zigbee2mqtt/west",
                                                    payload=json.dumps({"power": w}).encode()))
    bus._on_message(None, None, SimpleNamespace(topic="zigbee2mqtt/other", payload=b'{"power": 5}'))
    store.flush(force=True)
    assert [w for _, _, w in store.power_since(0)] == [80.0, 1450.0, 1460.0, 82.0]
    start, end = last_brew(connect(tmp / "kahvi.db", readonly=True), "west")
    assert end is not None and end >= start
    # a restart refills the graph's power strip from the store
    bus2 = PowerBus(devices={"left": "west"})
    bus2.seed(store.power_since(0))
    assert len(bus2.history("left", since_wall=0)) == 4


def test_day_buffer_seeds_today_only():
    store, clock, _ = _store()
    store.add(_rec(T0 - 86400, 0))                    # yesterday
    store.add(_rec(T0 - 60, 1))
    store.add({"t": iso_utc(T0 - 30), "seq": 2, "src": "sampler", "state": "dark", "luma": 3.0})
    store.flush(force=True)
    buf = DayBuffer()
    assert buf.seed(store, T0) == 1


def test_filter_state_round_trips():
    cal = Calibration()
    a, b = PotRBPF(cal, n_particles=50, seed=1), PotRBPF(cal, n_particles=50, seed=2)
    a.step(10.0, power_w=1450.0)
    assert b.load_bytes(a.state_bytes())
    assert np.array_equal(a.v, b.v) and np.array_equal(a.mode, b.mode)
    assert not PotRBPF(cal, n_particles=60).load_bytes(a.state_bytes())   # wrong size: refused
    store, clock, _ = _store()
    store.save_filter("left", T0, a.state_bytes())
    t, blob = store.load_filters()["left"]
    assert t == T0 and PotRBPF(cal, n_particles=50).load_bytes(blob)


def test_import_is_idempotent_and_export_matches(tmp_path):
    jsonl = tmp_path / "readings.jsonl"
    jsonl.write_text("\n".join(json.dumps(_rec(T0 + i, i)) for i in range(3)) + "\n{trunc", encoding="utf-8")
    csvp = tmp_path / "power_vasen.csv"
    csvp.write_text("timestamp,power\n2026-10-16T08:13:53+00:00,1604.0\n\0\0\0"   # NULs: a power cut
                    "2026-10-16T08:17:29+00:00,0.0\n")
    brews = tmp_path / "brews_vasen.jsonl"
    brews.write_text(json.dumps({"event": "start", "t": "2026-10-16T08:13:53+00:00", "power": 1604.0}) + "\n"
                     + json.dumps({"event": "end", "start": "2026-10-16T08:13:53+00:00",
                                   "end": "2026-10-16T08:17:29+00:00", "duration_s": 216.0,
                                   "peak_w": 1604.0}) + "\n")
    conn = connect(tmp_path / "k.db")
    assert kahvidb.import_readings(conn, [jsonl]) == 3
    assert kahvidb.import_readings(conn, [jsonl]) == 0
    assert kahvidb.import_power(conn, "west", csvp) == 2
    assert kahvidb.import_power(conn, "west", csvp) == 0
    assert kahvidb.import_brews(conn, "west", brews) == 1
    assert kahvidb.import_brews(conn, "west", brews) == 0
    out = io.StringIO()
    assert kahvidb.export_readings(conn, 0, out) == 3
    assert [json.loads(l)["seq"] for l in out.getvalue().splitlines()] == [0, 1, 2]
    assert kahvidb.stats(conn)["brews"]["rows"] == 1
