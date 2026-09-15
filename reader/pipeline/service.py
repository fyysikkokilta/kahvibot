"""ReaderService: the one process that owns the camera and the model.

Loop (cooperative, single thread):
  * a sampling tick every `interval` s while lit, `dark_interval` while dark or
    blind; a tick is capture -> luma -> dark gate -> (detect every N) -> read
    TTA=1 -> record;
  * requests from the bot are served between ticks: `frame(max_age)` returns
    the last lit frame if it is young enough, otherwise captures now; the frame
    goes back immediately (photo-first) and its reading is produced right after
    and appended as a `src: bot` record;
  * `graph()` renders from the in-memory day buffer through GraphCache.

Design deltas vs sampler.py (SAMPLER.md) called out inline as DELTA.
"""
from __future__ import annotations

import collections
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from .camera import CaptureBusy, CaptureFailed, Frame
from .gate import Gate
from .graphing import DayBuffer, GraphCache
from .power import PowerTail
from .rbpf import Calibration as RbpfCalibration, PotRBPF
from .store import ReadingsStore, iso_utc, slim

log = logging.getLogger("kahvi.service")

SIDES = ("left", "right")


class DarkGate:
    def __init__(self, enter=28.0, leave=45.0):
        self.enter, self.leave, self.dark = enter, leave, False

    def update(self, luma: float) -> bool:
        if self.dark:
            if luma > self.leave:
                self.dark = False
        elif luma < self.enter:
            self.dark = True
        return self.dark


class FailBackoff:
    STEPS = (10.0, 20.0, 40.0, 80.0, 160.0, 300.0)

    def __init__(self):
        self.fails = 0

    def fail(self):
        self.fails += 1
        return self.delay()

    def ok(self):
        self.fails = 0

    def delay(self):
        return 0.0 if not self.fails else self.STEPS[min(self.fails - 1, len(self.STEPS) - 1)]

    @property
    def active(self):
        return self.fails > 0


class BoxCache:
    def __init__(self, keep=5):
        self.hist = {s: collections.deque(maxlen=keep) for s in SIDES}

    def add(self, dets):
        for d in dets:
            self.hist[d["side"]].append((d["box"], d["score"]))

    def has_any(self):
        return any(self.hist[s] for s in SIDES)

    def working(self):
        out = []
        for side in SIDES:
            h = self.hist[side]
            if not h:
                continue
            boxes = np.asarray([b for b, _ in h], dtype=np.float64)
            out.append({"side": side,
                        "box": [round(float(v), 2) for v in np.median(boxes, axis=0)],
                        "score": round(float(np.median([s for _, s in h])), 4)})
        return out

    def clear(self):
        for h in self.hist.values():
            h.clear()


@dataclass
class ServiceConfig:
    interval: float = 10.0
    dark_interval: float = 60.0
    detect_every: int = 6
    tta_probe_every: int = 0          # DELTA: default off; each probe cost ~100 s on the Pi
    blind_after_nodetect: int = 30    # DELTA: back off on "no carafe", not "no ok reading"
    jump_ml: float = 300.0
    reuse_max_age: float = 15.0
    # how stale a held frame may be before it is worth making the caller
    # wait for a new capture instead
    stale_max_age: float = 90.0       # bot frames younger than this are reused
    request_tta: int = 1              # DELTA: no TTA in the request path
    flush_sec: float = 60.0
    graph_ttl_s: float = 600.0
    agree_window_s: float = 60.0      # a previous reading this recent defines 'agreement'
    # (volume, temperature) filter. Off by default: it needs a model bundle
    # exporting line_logits, and without one every reading is unchanged.
    filter_enabled: bool = False
    filter_particles: int = 800
    power_dir: str = ""
    calibration_path: str = ""
    power_devices: dict = field(default_factory=lambda: {"left": "vasen", "right": "oikea"})
    full_ml: float = 1250.0


@dataclass
class Stats:
    ticks: int = 0
    ticks_dark: int = 0
    ticks_skipped_busy: int = 0
    ticks_failed: int = 0
    requests: int = 0
    requests_reused: int = 0
    requests_captured: int = 0
    captures: int = 0
    tick_gaps: list = field(default_factory=list)      # virtual seconds between lit ticks
    request_photo_latency: list = field(default_factory=list)
    request_reading_latency: list = field(default_factory=list)
    compute_charged: float = 0.0                        # virtual seconds of compute


@dataclass
class FrameResult:
    frame: Frame
    pots: list
    age_s: float
    reused: bool
    seq: int


class ReaderService:
    def __init__(self, camera, reader, store: ReadingsStore, clock, gate: Gate,
                 cfg: ServiceConfig = ServiceConfig(), graphs_mod=None, font_dir=None):
        self.camera, self.reader, self.store, self.clock = camera, reader, store, clock
        self.gate, self.cfg = gate, cfg
        self.darkgate, self.backoff, self.boxcache = DarkGate(), FailBackoff(), BoxCache()
        self.seq = 0
        self.reading_n = 0
        self.force_detect = True
        self.consec_nodetect = 0
        self.blind = False
        self.last_ml: dict = {}
        self.prev_h: dict = {}          # side -> (mono, h) of the previous reading, for agreement
        self.last_lit: Optional[FrameResult] = None
        self.last_lit_tick_mono: Optional[float] = None
        self.next_tick_mono = clock.mono()
        self.daybuf = DayBuffer()
        # One filter per pot. Volume is sampled because its observation is
        # multimodal; temperature rides along in a Kalman filter inside each
        # particle, because it has no sensor and sampling it would waste them.
        self.filters = {}
        self.power = None
        if cfg.filter_enabled:
            try:
                cal = RbpfCalibration(cfg.calibration_path)
                self.filters = {s: PotRBPF(cal, n_particles=cfg.filter_particles, seed=i)
                                for i, s in enumerate(("left", "right"))}
                self.power = PowerTail(cfg.power_dir, cfg.power_devices, clock=clock)
                log.info("(volume, temperature) filter on: %d particles/pot, power from %s",
                         cfg.filter_particles, cfg.power_dir or "(none)")
            except Exception:  # noqa: BLE001 - a missing filter must not stop the reader
                log.warning("filter unavailable; readings stay unfiltered", exc_info=True)
                self.filters = {}
        self.filter_mono = None
        self.graphcache = GraphCache(graphs_mod, gate, cfg.graph_ttl_s, font_dir) if graphs_mod else None
        self.stats = Stats()

    # -- helpers --------------------------------------------------------------

    def _charge(self, local_seconds: float) -> None:
        self.stats.compute_charged += self.clock.charge(local_seconds)

    def cadence(self) -> float:
        if self.backoff.active:
            return self.backoff.delay()
        if self.darkgate.dark or self.blind:
            return self.cfg.dark_interval
        return self.cfg.interval

    def _capture(self) -> Optional[Frame]:
        try:
            fr = self.camera.capture()
        except CaptureBusy:
            self.stats.ticks_skipped_busy += 1
            return None
        except CaptureFailed:
            self.stats.ticks_failed += 1
            self.backoff.fail()
            return None
        self.stats.captures += 1
        if self.backoff.active:
            self.backoff.ok()
        return fr

    def _read(self, frame: Frame, tta: int, force_detect: bool = False):
        """Detect (amortised) + read. Returns pots (gate-annotated) or None."""
        rgb = frame.rgb()
        if rgb is None:
            self.backoff.fail()
            return None
        need_detect = (force_detect or self.force_detect or not self.boxcache.has_any()
                       or self.reading_n % self.cfg.detect_every == 0)
        if need_detect:
            dets, dt = self.reader.detect_timed(rgb, ident=frame.ident)
            self._charge(dt)
            self.force_detect = False
            if dets:
                self.consec_nodetect = 0
                self.boxcache.add(dets)
            else:
                self.consec_nodetect += 1
                if self.consec_nodetect >= 3:
                    self.boxcache.clear()
        dets = self.boxcache.working()
        pots, dt = self.reader.read_pots(rgb, dets, tta, ident=frame.ident,
                                         with_rows=bool(self.filters)) if dets else ([], 0.0)
        self._charge(dt)
        self.reading_n += 1
        # temporal agreement with the previous reading of the same pot (gate.py)
        now = frame.captured_mono
        for p in pots:
            prev = self.prev_h.get(p["side"])
            if prev is not None and now - prev[0] <= self.cfg.agree_window_s:
                p["agree"] = round(abs(p["h"] - prev[1]) * self.cfg.full_ml, 1)
            else:
                p["agree"] = None
            self.prev_h[p["side"]] = (now, p["h"])
        self.gate.apply(pots)
        for p in pots:
            if p["ok"]:
                prev = self.last_ml.get(p["side"])
                if prev is not None and abs(p["ml"] - prev) > self.cfg.jump_ml:
                    self.force_detect = True
                self.last_ml[p["side"]] = p["ml"]
        self._step_filters(pots, now)
        # DELTA: blind = no carafe detected for a long time, not "no ok reading"
        if not dets:
            if self.consec_nodetect >= self.cfg.blind_after_nodetect and not self.blind:
                self.blind = True
                log.info("no carafe detected for %d ticks; cadence %.0f s",
                         self.consec_nodetect, self.cfg.dark_interval)
        elif self.blind:
            self.blind = False
            log.info("carafe detected again; cadence %.0f s", self.cfg.interval)
        return pots

    def _step_filters(self, pots, now_mono: float) -> None:
        """Advance each pot's filter and hang its posterior on the reading.

        The row distribution enters as a likelihood, so a diffuse frame widens
        the posterior instead of being discarded, and the plug's wattage pins the
        regime: the level may only rise while the element is drawing. Failure
        here is never fatal - the unfiltered reading is still a reading.
        """
        if not self.filters:
            return
        dt = 0.0 if self.filter_mono is None else max(now_mono - self.filter_mono, 0.0)
        self.filter_mono = now_mono
        seen = {p["side"] for p in pots}
        for side, filt in self.filters.items():
            try:
                pot = next((p for p in pots if p["side"] == side), None)
                watts = self.power.watts(side) if self.power is not None else None
                post = filt.step(dt=min(dt, 300.0), power_w=watts,
                                 rowdist=(pot or {}).get("rowdist"),
                                 surface_logit=(pot or {}).get("v"))
                if pot is not None:
                    pot["temp_c"] = round(post.temp_mean, 1)
                    pot["f_ml"] = round(post.ml_median, 1)
                    pot["f_lo"] = round(post.ml_lo, 1)
                    pot["f_hi"] = round(post.ml_hi, 1)
                    pot["brewing"] = bool(post.brewing)
            except Exception:  # noqa: BLE001
                log.warning("filter step failed for %s", side, exc_info=True)
        for p in pots:
            p.pop("rowdist", None)          # never goes in the log: 3x256 floats per pot
        _ = seen

    def _record(self, frame: Frame, luma: float, pots, src: str, tta: int) -> dict:
        rec = {"t": iso_utc(frame.captured_wall), "seq": self.seq, "src": src,
               "luma": round(luma, 1), "pots": slim(pots)}
        if tta > 1:
            rec["tta"] = tta
        usable = any(self.gate.usable(p) for p in pots)
        self.store.add(rec, usable=usable)
        self.daybuf.add(rec, frame.captured_wall)
        self.seq += 1
        return rec

    # -- sampling -------------------------------------------------------------

    def tick(self) -> None:
        self.stats.ticks += 1
        fr = self._capture()
        if fr is None:
            return
        luma = fr.luma()
        if luma is None:
            self.stats.ticks_failed += 1
            self.backoff.fail()
            return
        was_dark = self.darkgate.dark
        dark = self.darkgate.update(luma)
        if dark != was_dark:
            log.info("%s (luma %.1f)", "dark" if dark else "light again", luma)
            if not dark:
                self.force_detect = True
        if dark:
            self.stats.ticks_dark += 1
            rec = {"t": iso_utc(fr.captured_wall), "seq": self.seq, "src": "sampler",
                   "state": "dark", "luma": round(luma, 1)}
            self.store.add(rec)
            self.daybuf.add(rec, fr.captured_wall)
            self.seq += 1
            return
        tta = 8 if (self.cfg.tta_probe_every and self.reading_n % self.cfg.tta_probe_every == 0) else 1
        pots = self._read(fr, tta)
        if pots is None:
            return
        seq = self.seq
        self._record(fr, luma, pots, "sampler", tta)
        # cadence is measured capture-to-capture, not end-to-end, so a slow
        # detect tick does not masquerade as a cadence change
        if self.last_lit_tick_mono is not None:
            self.stats.tick_gaps.append(fr.captured_mono - self.last_lit_tick_mono)
        self.last_lit_tick_mono = fr.captured_mono
        self.last_lit = FrameResult(fr, pots, 0.0, False, seq)

    def run_due(self, until_mono: Optional[float] = None) -> None:
        """Run every tick whose time has come (the gym calls this before each
        request; the daemon loop calls it every pass)."""
        while True:
            now = self.clock.mono()
            if until_mono is None:
                if self.next_tick_mono > now:
                    return                       # daemon: nothing due yet
            else:
                if self.next_tick_mono > until_mono:
                    return                       # gym: next tick is after the horizon
                if self.next_tick_mono > now:
                    self.clock.advance(self.next_tick_mono - now)   # jump to the tick instant
            start = self.clock.mono()
            self.tick()
            self.store.flush()
            now = self.clock.mono()
            target = start + self.cadence()
            self.next_tick_mono = target if target > now else now + self.cadence()

    def seconds_to_next_tick(self) -> float:
        return max(0.0, self.next_tick_mono - self.clock.mono())

    # -- requests ---------------------------------------------------------------

    def frame(self, max_age: Optional[float] = None) -> Optional[FrameResult]:
        """Bot request. Photo-first: the returned FrameResult's frame is ready
        as soon as capture finishes; its pots are the fresh reading (computed
        right after, charged to the clock, recorded as src=bot)."""
        self.stats.requests += 1
        t_req = self.clock.mono()
        max_age = self.cfg.reuse_max_age if max_age is None else max_age
        if self.last_lit is not None:
            age = self.clock.mono() - self.last_lit.frame.captured_mono
            if age <= max_age:
                self.stats.requests_reused += 1
                self.stats.request_photo_latency.append(0.0)
                self.stats.request_reading_latency.append(0.0)
                return FrameResult(self.last_lit.frame, self.last_lit.pots, age, True, self.last_lit.seq)
        # One attempt first. Retrying costs a second each time, and the bot's
        # socket timeout is shorter than three retries plus a capture, so a busy
        # camera used to blow the deadline and the request was lost anyway.
        # A frame we already hold beats a frame that arrives after the caller
        # has given up.
        fr = self._capture()
        if fr is None and self.last_lit is not None:
            age = self.clock.mono() - self.last_lit.frame.captured_mono
            if age <= self.cfg.stale_max_age:
                self.stats.requests_reused += 1
                return FrameResult(self.last_lit.frame, self.last_lit.pots, age, True,
                                   self.last_lit.seq)
        for _ in range(2):
            if fr is not None:
                break
            self.clock.sleep(1.0)           # nothing usable in hand: keep trying
            fr = self._capture()
        if fr is None:
            # The camera is busy - usually this service's own tick holds the
            # lock. Returning None sends the bot off to a cold fswebcam plus a
            # cold model read, which is slower and produces a worse reading than
            # the frame already in hand. Hand back what we have, with its true
            # age, and let the caller decide.
            if self.last_lit is not None:
                self.stats.requests_reused += 1
                age = self.clock.mono() - self.last_lit.frame.captured_mono
                return FrameResult(self.last_lit.frame, self.last_lit.pots, age, True,
                                   self.last_lit.seq)
            return None
        self.stats.requests_captured += 1
        photo_ready = self.clock.mono()
        luma = fr.luma() or 0.0
        pots = self._read(fr, self.cfg.request_tta, force_detect=False) or []
        seq = self.seq
        if not self.darkgate.update(luma):
            self._record(fr, luma, pots, "bot", self.cfg.request_tta)
            self.last_lit = FrameResult(fr, pots, 0.0, False, seq)
            # DELTA: a bot frame is a sample too; push the next tick out one interval
            self.next_tick_mono = max(self.next_tick_mono, self.clock.mono() + self.cfg.interval)
        self.stats.request_photo_latency.append(photo_ready - t_req)
        self.stats.request_reading_latency.append(self.clock.mono() - t_req)
        return FrameResult(fr, pots, 0.0, False, seq)

    def graph(self):
        if self.graphcache is None:
            return None, "graph disabled"
        return self.graphcache.get(self.daybuf, self.store.latest["last_usable_seq"], self.clock)
