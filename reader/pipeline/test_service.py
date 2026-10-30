"""Unit tests for ReaderService scheduling with a fake camera and reader
(no model, no files beyond a temp dir). Run: cd reader && python -m pytest pipeline"""
from __future__ import annotations

import io
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.camera import CaptureFailed, Frame        # noqa: E402
from pipeline.clock import VirtualClock                 # noqa: E402
from pipeline.gate import Gate                          # noqa: E402
from pipeline.service import ReaderService, ServiceConfig  # noqa: E402
from pipeline.store import ReadingsStore                # noqa: E402


def _jpeg(grey: int) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 48), (grey, grey, grey)).save(buf, "JPEG")
    return buf.getvalue()


class FakeCamera:
    def __init__(self, clock, grey=120, cost=2.0):
        self.clock, self.grey, self.cost, self.n = clock, grey, cost, 0

    def capture(self):
        w, m = self.clock.wall(), self.clock.mono()
        self.clock.sleep(self.cost)
        self.n += 1
        return Frame(_jpeg(self.grey), w, m, ident=f"f{self.n}")


class FakeReader:
    """Two pots, entropy configurable; costs 0.1 local s per call."""

    def __init__(self, e=0.5, dets=True):
        self.e, self.dets, self.calls = e, dets, 0

    def detect_timed(self, rgb, ident=None):
        self.calls += 1
        if not self.dets:
            return [], 0.05
        return [{"side": "left", "box": [0, 0, 30, 40], "score": 0.9},
                {"side": "right", "box": [34, 0, 64, 40], "score": 0.9}], 0.05

    def read_pots(self, rgb, dets, tta=1, ident=None, **kw):
        self.calls += 1
        return [{"side": d["side"], "h": 0.3, "e": self.e, "d": d["score"], "ml": 375.0,
                 "fill": 0.3, "box": d["box"], "rows": {"base": 40, "top": 0, "surf": 28}} for d in dets], 0.1


def make(e=0.5, grey=120, dets=True, cfg=None, scale=10.0):
    clock = VirtualClock(1_800_000_000.0, scale=scale)
    tmp = Path(tempfile.mkdtemp())
    store = ReadingsStore(tmp / "kahvi.db", clock, flush_sec=60)
    svc = ReaderService(FakeCamera(clock, grey), FakeReader(e, dets), store, clock, Gate(0.55, 0.62), cfg or ServiceConfig())
    return svc, clock, store


def test_ticks_keep_cadence_and_record():
    svc, clock, store = make()
    svc.run_due(until_mono=300)
    assert svc.stats.ticks >= 25                       # 10 s cadence over 300 s, ticks take ~3 s
    gaps = svc.stats.tick_gaps
    assert 10 <= min(gaps) <= 14 and max(gaps) <= 15
    assert store.records == svc.stats.ticks
    assert store.latest["last_usable_seq"] >= 0        # e=0.5 <= 0.55 -> ok


def test_dark_gate_slows_and_skips_reader():
    svc, clock, store = make(grey=3)
    svc.run_due(until_mono=600)
    assert svc.stats.ticks_dark == svc.stats.ticks
    assert svc.reader.calls == 0
    assert 55 <= min(svc.stats.tick_gaps or [60]) if svc.stats.tick_gaps else True
    assert svc.cadence() == 60.0


def test_request_reuses_fresh_frame_then_captures():
    svc, clock, store = make()
    svc.run_due(until_mono=0)                          # first tick at t=0
    r = svc.frame(max_age=15)
    assert r.reused and r.age_s <= 5 and r.pots and r.pots[0]["ok"]
    clock.advance(40)                                  # no tick ran meanwhile
    r2 = svc.frame(max_age=15)
    assert not r2.reused and svc.stats.requests_captured == 1
    assert svc.stats.request_photo_latency[-1] == 2.0  # capture cost only (photo-first)
    assert svc.stats.request_reading_latency[-1] > 2.0
    store.flush(force=True)
    assert any(r["src"] == "bot" for r in store.records_since(0))


def test_blind_backoff_on_no_carafe_not_on_abstention():
    # high entropy but carafes detected: must NOT go blind (the legacy rule did)
    svc, clock, store = make(e=0.9)
    svc.run_due(until_mono=600)
    assert not svc.blind and svc.cadence() == 10.0
    # no carafe detected at all: goes blind after N ticks
    svc2, clock2, _ = make(dets=False, cfg=ServiceConfig(blind_after_nodetect=5))
    svc2.run_due(until_mono=300)
    assert svc2.blind and svc2.cadence() == 60.0


def test_gate_tiers_are_downstream():
    g = Gate(0.55, 0.62)
    assert g.tier(0.5) == "ok" and g.tier(0.6) == "uncertain" and g.tier(0.7) == "abstain"
    pots = g.apply([{"e": 0.6}])
    assert pots[0]["tier"] == "uncertain" and pots[0]["ok"] is False and g.usable(pots[0])


def test_agreement_gate_uses_neighbour_then_falls_back():
    g = Gate(0.55, 0.62, mode="agree", agree_ok_ml=40, agree_unc_ml=90)
    assert g.tier_pot({"e": 0.9, "agree": 10.0}) == "ok"          # consistent beats diffuse
    assert g.tier_pot({"e": 0.5, "agree": 300.0}) == "abstain"    # a jump beats sharp
    assert g.tier_pot({"e": 0.5, "agree": None}) == "ok"          # no neighbour: entropy decides
    # the service fills 'agree' from the previous tick of the same pot
    svc, clock, store = make(e=0.9, cfg=ServiceConfig())
    svc.gate = g
    svc.run_due(until_mono=25)                                      # ticks at 0 and 10 and 20
    assert svc.last_lit.pots[0]["agree"] == 0.0                     # fake reader is constant
    assert svc.last_lit.pots[0]["tier"] == "ok"
    store.flush(force=True)
    assert any(p.get("a") == 0.0 for r in store.records_since(0) for p in r.get("pots", []))


class WedgedCamera(FakeCamera):
    """Fails every capture until reset() has run `fix_after` times."""

    def __init__(self, clock, fix_after=1, reset_ok=True):
        super().__init__(clock)
        self.resets, self.fix_after, self.reset_ok = 0, fix_after, reset_ok

    def capture(self):
        if self.resets < self.fix_after:
            self.clock.sleep(8.0)
            raise CaptureFailed("empty frame (exit 0): Timed out waiting for frame!")
        return super().capture()

    def reset(self):
        self.resets += 1
        return self.reset_ok, "reset 1-1.3 041e:4095"


def test_wedged_camera_is_reset_then_recovers(caplog):
    svc, clock, store = make()
    svc.camera = WedgedCamera(clock)
    with caplog.at_level("INFO", logger="kahvi.service"):
        svc.run_due(until_mono=600)
    assert svc.camera.resets == 1 and svc.stats.camera_resets == 1
    assert svc.stats.ticks_failed == svc.cfg.camera_reset_after
    assert svc.capture_fails == 0 and not svc.backoff.active
    assert svc.cadence() == 10.0                       # back to normal, not stuck at 300 s
    text = caplog.text
    assert "Timed out waiting for frame!" in text      # the reason reaches the journal
    assert "camera reset: reset 1-1.3" in text
    assert "camera back after 3 failed captures" in text


def test_reset_is_rate_limited_while_the_camera_stays_dead():
    svc, clock, store = make(cfg=ServiceConfig(camera_reset_every_s=900.0))
    svc.camera = WedgedCamera(clock, fix_after=10**6, reset_ok=False)
    svc.run_due(until_mono=3000)
    assert svc.stats.ticks_failed > 10
    assert 2 <= svc.camera.resets <= 4                 # ~once per 900 s, not once per failure


def test_camera_without_reset_still_backs_off():
    class Dead(FakeCamera):
        def capture(self):
            raise CaptureFailed("fswebcam timed out after 8 s")
    svc, clock, store = make()
    svc.camera = Dead(clock)
    svc.run_due(until_mono=1200)
    assert svc.stats.camera_resets == 0 and svc.cadence() == 300.0


def test_fswebcam_failure_carries_its_stderr(monkeypatch, tmp_path):
    import subprocess as sp
    from pipeline import camera as cam

    def fake_run(cmd, **kw):
        Path(cmd[-1]).write_bytes(b"")                 # what fswebcam 20140113 leaves
        return sp.CompletedProcess(cmd, 0, None, b"--- Opening /dev/video0...\nTimed out waiting for frame!\n")
    monkeypatch.setattr(cam.subprocess, "run", fake_run)
    c = cam.FswebcamCamera(VirtualClock(0.0), lock_path="", tmp_path=str(tmp_path / "f.jpg"))
    try:
        c.capture()
    except CaptureFailed as e:
        assert str(e) == "empty frame (exit 0): Timed out waiting for frame!"
    else:
        raise AssertionError("an empty frame must fail")
    assert c.reset() == (False, "no reset command configured")
