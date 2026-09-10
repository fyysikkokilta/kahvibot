"""Continuous background coffee-level sampler. Deployment entry point.

Implements SAMPLER.md: a resident daemon that captures a frame every ~10 s
with byte-identical fswebcam arguments to the bot, reads it with TTA off and
the detector amortised to one tick in six, keeps frames on tmpfs only, and
appends slim JSONL records to the same readings file the bot writes.

Lives beside read_frame.py in the reader deployment directory (NOT in the
kahvibot repo) and imports the verified preprocessing/model code from it.
Run under systemd as kahvisampler.service (Type=notify, watchdog, SCHED_IDLE,
CPUQuota, MemoryMax) — see kahvisampler.service and install_sampler.sh.

Containment invariant, inherited from read_coffee_level(): any failure
degrades to "no record for that tick" — never a crash loop, a log flood, a
held camera, or a wrong number. One log line per state change, never per tick.

Kill switch: touch /etc/kahvi-sampler/disabled and the daemon exits cleanly.
"""
from __future__ import annotations

import argparse
import collections
import json
import logging
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image

# fcntl is POSIX-only; every camera/lock path is too. Guarded so the pure
# logic in this file stays importable (and testable) off the Pi.
try:
    import fcntl
except ImportError:  # pragma: no cover - Windows dev box
    fcntl = None

sys.path.insert(0, str(Path(__file__).resolve().parent))
from read_frame import (  # noqa: E402
    SIDES,
    FrameReader,
    area_resize,
    geometric,
    load_rgb,
    model_crop,
    photometric,
    to_chw,
)

log = logging.getLogger("kahvisampler")

# Records must never be stamped with an implausible wall clock (Pi 3B has no
# RTC). Compiled-in floor per SAMPLER.md §8: 2026-08-01T00:00:00Z.
CLOCK_FLOOR = 1785542400.0

FRAME_RING_SLOTS = 24  # ~4 min of pre-roll on tmpfs, hard file count


# --------------------------------------------------------------------------
# pure-logic state machines (unit-testable off the Pi)
# --------------------------------------------------------------------------

class DarkGate:
    """Hysteresis gate on mean luma: enter dark below 28, leave above 45."""

    def __init__(self, enter: float = 28.0, leave: float = 45.0):
        self.enter = enter
        self.leave = leave
        self.dark = False

    def update(self, luma: float) -> bool:
        if self.dark:
            if luma > self.leave:
                self.dark = False
        elif luma < self.enter:
            self.dark = True
        return self.dark


class FailBackoff:
    """Exponential capture-failure backoff 10->20->40->...->300 s."""

    STEPS = (10.0, 20.0, 40.0, 80.0, 160.0, 300.0)

    def __init__(self):
        self.fails = 0

    def fail(self) -> float:
        self.fails += 1
        return self.delay()

    def ok(self):
        self.fails = 0

    def delay(self) -> float:
        if self.fails == 0:
            return 0.0
        return self.STEPS[min(self.fails - 1, len(self.STEPS) - 1)]

    @property
    def active(self) -> bool:
        return self.fails > 0


class BoxCache:
    """Rolling median of the last N detections per side (SAMPLER.md §5)."""

    def __init__(self, keep: int = 5):
        self.hist = {s: collections.deque(maxlen=keep) for s in SIDES}

    def add(self, dets):
        for d in dets:
            self.hist[d["side"]].append((d["box"], d["score"]))

    def has_any(self) -> bool:
        return any(self.hist[s] for s in SIDES)

    def working(self):
        dets = []
        for side in SIDES:
            h = self.hist[side]
            if not h:
                continue
            boxes = np.asarray([b for b, _ in h], dtype=np.float64)
            box = [round(float(v), 2) for v in np.median(boxes, axis=0)]
            score = round(float(np.median([s for _, s in h])), 4)
            dets.append({"side": side, "box": box, "score": score})
        return dets

    def clear(self):
        for h in self.hist.values():
            h.clear()


class RetentionPolicy:
    """Stratified-by-predicted-fill daily quotas (SAMPLER.md §6).

    The corpus is 85% empty and has almost nothing above 0.6 fill, so the
    quota concentrates where the corpus is empty. Roughly 40 frames/day.
    """

    BANDS = (  # (lo, hi, frames/day)
        (0.60, 1.01, 200),  # the hole: take everything (safety cap)
        (0.38, 0.60, 10),
        (0.12, 0.38, 30),   # the band where checkpoints disagree most
        (-0.01, 0.12, 5),   # token handful; 6,801 exist already
    )

    def __init__(self):
        self.day = None
        self.counts = [0] * len(self.BANDS)

    def decide(self, fill: float, day: str) -> bool:
        if day != self.day:
            self.day = day
            self.counts = [0] * len(self.BANDS)
        for i, (lo, hi, quota) in enumerate(self.BANDS):
            if lo <= fill < hi:
                if self.counts[i] < quota:
                    self.counts[i] += 1
                    return True
                return False
        return False


class ClockGuard:
    """Monotonic scheduling, plausible-wall-clock stamping, step detection."""

    def __init__(self, floor: float = CLOCK_FLOOR):
        self.floor = floor
        self.base_wall = time.time()
        self.base_mono = time.monotonic()

    def plausible(self) -> bool:
        return time.time() >= self.floor

    def check_step(self) -> bool:
        """True once per wall-clock step > 2 s (e.g. first NTP sync)."""
        drift = (time.time() - self.base_wall) - (time.monotonic() - self.base_mono)
        if abs(drift) > 2.0:
            self.base_wall = time.time()
            self.base_mono = time.monotonic()
            return True
        return False

    def stamp(self, mono: float) -> float:
        """Wall time for a past monotonic instant, using the current clock."""
        return time.time() - (time.monotonic() - mono)


def next_target(tick_start: float, cadence: float, now: float) -> float:
    """Next tick on the monotonic clock; overruns drop the tick, never queue."""
    target = tick_start + cadence
    if target <= now:
        return now + cadence
    return target


def iso_utc(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat(timespec="seconds")


def luma_of(path) -> "float | None":
    """Mean luma via PIL's 1/8-scale DCT draft decode (~1.4 ms, SAMPLER.md §7).

    Doubles as the decode check for fswebcam's known write-garbage failure
    mode; returns None when the file does not decode.
    """
    try:
        with Image.open(path) as im:
            im.draft("L", (160, 96))
            arr = np.asarray(im.convert("L"), dtype=np.float32)
        if arr.size == 0:
            return None
        return float(arr.mean())
    except (OSError, ValueError, SyntaxError):
        return None


def slim_pots(pots):
    return [{"s": p["side"], "ok": p["ok"], "ml": p["volume_ml"],
             "h": p["h_norm"], "e": p["surface_entropy"],
             "d": p["detector_score"]} for p in pots]


# --------------------------------------------------------------------------
# reader with injectable boxes (detection amortised across ticks)
# --------------------------------------------------------------------------

class SamplerReader(FrameReader):
    """FrameReader whose read step accepts cached detections and a per-call
    TTA view count. The result assembly mirrors FrameReader.read() exactly so
    sampler and bot records stay one comparable series."""

    def read_pots(self, rgb: np.ndarray, dets, tta_views: int):
        if not dets:
            return []
        cache_crops, transforms = [], []
        for det in dets:
            crop, tf = model_crop(rgb, det["box"], out_size=(self.cache_w, self.cache_h))
            cache_crops.append(crop)
            transforms.append(tf)

        base = np.stack([to_chw(area_resize(c, self.crop_w, self.rows))
                         for c in cache_crops])
        out = self._run_reader(base)

        tta_h = None
        if tta_views > 1:
            views = []
            for v in range(tta_views):
                rng = np.random.default_rng(1000 + v)
                for crop in cache_crops:
                    warped = geometric(crop, rng, (self.crop_w, self.rows), self.tta_strength)
                    views.append(to_chw(photometric(warped, rng, self.tta_strength)))
            h_all = self._run_reader(np.stack(views))["h_norm"]
            tta_h = np.median(h_all.reshape(tta_views, len(dets)), axis=0)

        results = []
        for i, det in enumerate(dets):
            h = float(out["h_norm"][i]) if tta_h is None else float(tta_h[i])
            surf_ent = float(out["entropy"][i, 2])
            clean = surf_ent <= self.gate_entropy
            ml = self.cal.ml(h)
            scale, off_x, off_y, pad_x, pad_y = transforms[i]

            def frame_y(y_norm: float) -> float:
                return (float(y_norm) * self.cache_h - pad_y) / scale + off_y

            results.append({
                "side": det["side"],
                "ok": bool(clean),
                "volume_ml": round(ml, 1) if clean else None,
                "fill_fraction": round(self.cal.fraction(h), 4) if clean else None,
                "cups": round(ml / 125.0, 2) if clean else None,
                "h_norm": round(h, 5),
                "surface_entropy": round(surf_ent, 4),
                "detector_score": det["score"],
                "box": det["box"],
                "rows_frame_px": {
                    "base": round(frame_y(out["y_base"][i]), 1),
                    "top": round(frame_y(out["y_top"][i]), 1),
                    "surf": round(frame_y(out["y_surf"][i]), 1),
                },
                "reason": None if clean else
                          "diffuse surface estimate (occluded or no visible surface)",
            })
        return results


# --------------------------------------------------------------------------
# the daemon
# --------------------------------------------------------------------------

class Sampler:
    def __init__(self, args):
        self.args = args
        self.model_dir = Path(args.model_dir).resolve()
        self.run_dir = Path(args.run_dir)
        self.state_dir = Path(args.state_dir)
        self.log_pattern = args.log
        self.lock_path = args.lock
        self.disable_file = Path(args.disable_file)
        w, h = args.resolution.lower().split("x")
        self.resolution = (int(w), int(h))

        self.clock = ClockGuard()
        self.darkgate = DarkGate()
        self.backoff = FailBackoff()
        self.boxcache = BoxCache()
        self.retention = RetentionPolicy()

        self.seq = 0            # monotonic tick counter, carried in records
        self.reading_n = 0      # lit, successfully captured ticks only
        self.force_detect = True
        self.consec_unusable = 0
        self.consec_nodetect = 0
        self.blind = False
        self.overruns = 0
        self.bad_records = 0
        self.dropped_prestamp = 0
        self.last_ml = {}       # side -> last ok millilitres
        self.last_ok = {}       # side -> last ok flag
        self.buf = collections.deque()
        self.last_flush_mono = time.monotonic()
        self._last_flush_mtime = 0.0
        self._persist_stopped = False
        self._clock_hold_logged = False
        self._lock_warned = False
        self._daemon_lock = None

        self.reader = None      # constructed in start()

    # -- systemd plumbing ---------------------------------------------------

    def notify(self, msg: str):
        addr = os.environ.get("NOTIFY_SOCKET")
        if not addr:
            return
        if addr.startswith("@"):
            addr = "\0" + addr[1:]
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
            try:
                s.sendto(msg.encode("ascii"), addr)
            finally:
                s.close()
        except OSError:
            pass

    def disabled(self) -> bool:
        return self.disable_file.exists()

    # -- capture ------------------------------------------------------------

    def capture(self, path: Path) -> str:
        """Grab one frame under a non-blocking flock. Returns ok|busy|fail.

        The lock is held only across fswebcam, never across inference, and a
        busy lock is a scheduling decision, not an error. Arguments are
        byte-identical to the bot's: the 6,001-frame training corpus IS the
        distribution these arguments produce, so -S 20 and 1280x720 must not
        be "optimised" (SAMPLER.md §3).
        """
        lock_fd = None
        try:
            if fcntl is not None and self.lock_path:
                try:
                    lock_fd = open(self.lock_path, "a+b")
                    fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError:
                    if lock_fd is not None:
                        lock_fd.close()
                        lock_fd = None
                        return "busy"     # bot has the camera
                    if not self._lock_warned:
                        self._lock_warned = True
                        log.warning("lock file %s unavailable; sampling without "
                                    "camera arbitration", self.lock_path)
            try:
                os.unlink(path)           # unlink before write: hard file count
            except OSError:
                pass
            w, h = self.resolution
            cmd = ["fswebcam", "--quiet", "-S", "20", "--no-banner",
                   "--resolution", f"{w}x{h}", str(path)]
            try:
                subprocess.run(cmd, timeout=8,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except (subprocess.TimeoutExpired, OSError):
                return "fail"             # run() SIGKILLs the child on timeout
            try:
                if os.path.getsize(path) == 0:
                    return "fail"
            except OSError:
                return "fail"
            return "ok"
        finally:
            if lock_fd is not None:
                try:
                    fcntl.flock(lock_fd, fcntl.LOCK_UN)
                except (OSError, ValueError):
                    pass
                lock_fd.close()

    def bot_wrote_recently(self) -> bool:
        """Skip a tick when a bot reading younger than ~8 s already exists."""
        try:
            mtime = Path(datetime.now().strftime(self.log_pattern)).stat().st_mtime
        except OSError:
            return False
        if abs(mtime - self._last_flush_mtime) < 0.5:
            return False                  # that was our own flush
        return (time.time() - mtime) < 8.0

    # -- persistence ----------------------------------------------------------

    def disk_ok(self) -> bool:
        if not hasattr(os, "statvfs"):
            return True
        try:
            st = os.statvfs(str(Path(datetime.now().strftime(self.log_pattern)).parent))
        except OSError:
            return True
        free_mb = st.f_bavail * st.f_frsize / 1e6
        ok = free_mb > self.args.min_free_mb
        if not ok and not self._persist_stopped:
            self._persist_stopped = True
            log.warning("below %d MB free: sampling continues, nothing is "
                        "persisted", self.args.min_free_mb)
        elif ok and self._persist_stopped:
            self._persist_stopped = False
            log.info("disk space recovered; persistence resumed")
        return ok

    def add_record(self, rec: dict, mono: float):
        rec["seq"] = self.seq
        rec["src"] = "sampler"
        if self.clock.plausible():
            rec["t"] = iso_utc(self.clock.stamp(mono))
        else:
            rec["_mono"] = mono           # stamped at flush once the clock syncs
        self.buf.append(rec)

    def flush(self, force: bool = False):
        now = time.monotonic()
        if not force and now - self.last_flush_mono < self.args.flush_sec:
            return
        self.last_flush_mono = now
        if not self.buf:
            return
        if not self.clock.plausible():
            if not self._clock_hold_logged:
                self._clock_hold_logged = True
                log.warning("wall clock implausible (no NTP yet); buffering "
                            "records, never stamping 1970")
            while len(self.buf) > 1000:
                self.buf.popleft()
                self.dropped_prestamp += 1
            return
        if self._clock_hold_logged:
            self._clock_hold_logged = False
            log.info("clock is plausible; %d buffered records released "
                     "(%d dropped)", len(self.buf), self.dropped_prestamp)
        if not self.disk_ok():
            self.buf.clear()
            return
        lines = []
        while self.buf:
            rec = self.buf.popleft()
            mono = rec.pop("_mono", None)
            if "t" not in rec and mono is not None:
                rec["t"] = iso_utc(self.clock.stamp(mono))
            try:
                # allow_nan=False: a NaN in a JSONL line breaks every consumer
                # downstream, silently, weeks later. Drop the record instead.
                lines.append(json.dumps(rec, allow_nan=False, separators=(",", ":")))
            except ValueError:
                self.bad_records += 1
        if not lines:
            return
        path = Path(datetime.now().strftime(self.log_pattern))
        try:
            # One batched append per flush interval, never fsync (SAMPLER.md §6):
            # fewer windows for a brownout to land on an in-flight write.
            with open(path, "a", encoding="utf-8") as fh:
                fh.write("\n".join(lines) + "\n")
            self._last_flush_mtime = path.stat().st_mtime
        except OSError:
            log.warning("readings append failed", exc_info=True)

    def persist_frame(self, slot: Path, full_rec: dict):
        if not self.clock.plausible() or not self.disk_ok():
            return
        try:
            d = self.state_dir / "retained"
            d.mkdir(parents=True, exist_ok=True)
            stem = "%s-%07d" % (
                full_rec["t"].replace(":", "").replace("-", "").replace("+0000", "Z"),
                self.seq)
            shutil.copyfile(slot, d / (stem + ".jpg"))
            (d / (stem + ".json")).write_text(
                json.dumps(full_rec, allow_nan=False), encoding="utf-8")
            self._enforce_ring(d)
        except (OSError, ValueError):
            log.warning("frame retention failed", exc_info=True)

    def _enforce_ring(self, d: Path):
        """Hard-capped FIFO ring: when full it rotates, it never grows."""
        entries = sorted(d.glob("*.jpg"))
        total = 0
        sizes = []
        for jpg in entries:
            side = jpg.with_suffix(".json")
            n = jpg.stat().st_size + (side.stat().st_size if side.exists() else 0)
            sizes.append((jpg, side, n))
            total += n
        cap = self.args.ring_mb * 1_000_000
        for jpg, side, n in sizes:
            if total <= cap:
                break
            for p in (jpg, side):
                try:
                    p.unlink()
                except OSError:
                    pass
            total -= n

    # -- the loop -------------------------------------------------------------

    def current_cadence(self) -> float:
        if self.backoff.active:
            return self.backoff.delay()
        if self.darkgate.dark:
            return self.args.dark_interval
        if self.blind:
            return self.args.dark_interval
        return self.args.interval

    def sleep_until(self, target: float) -> bool:
        """Chunked sleep that keeps the watchdog fed and the kill switch live."""
        while True:
            if self.disabled():
                return False
            now = time.monotonic()
            if now >= target:
                return True
            time.sleep(min(20.0, target - now))
            self.notify("WATCHDOG=1")

    def start(self):
        for name in ("reader.onnx", "fastbox.onnx", "calibration.json", "manifest.json"):
            p = self.model_dir / name
            if not p.is_file() or p.stat().st_size == 0:
                # Exit non-zero with one clear message; StartLimitBurst stops
                # the flapping. Never start and silently emit garbage.
                log.error("model artifact missing or empty: %s", p)
                return 3
        try:
            json.loads((self.model_dir / "manifest.json").read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            log.error("manifest.json unreadable: %s", exc)
            return 3

        self.run_dir.mkdir(parents=True, exist_ok=True)
        if fcntl is not None:
            self._daemon_lock = open(self.run_dir / "daemon.lock", "a+b")
            try:
                fcntl.flock(self._daemon_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                log.error("another sampler already holds %s", self.run_dir)
                return 4

        try:
            self.reader = SamplerReader(self.model_dir, threads=self.args.threads,
                                        tta_views=1)
        except Exception as exc:  # noqa: BLE001 - a broken install must say so
            log.error("model load failed: %s", exc)
            return 3

        log.info("sampler up: interval=%.0fs dark=%.0fs detect_every=%d "
                 "tta_probe_every=%d log=%s",
                 self.args.interval, self.args.dark_interval,
                 self.args.detect_every, self.args.tta_probe_every,
                 self.log_pattern)
        self.notify("READY=1")
        try:
            self.loop()
        finally:
            self.flush(force=True)
        log.info("sampler stopped cleanly (seq=%d overruns=%d bad_records=%d)",
                 self.seq, self.overruns, self.bad_records)
        return 0

    def loop(self):
        target = time.monotonic()
        while True:
            if not self.sleep_until(target):
                log.info("kill switch %s present; exiting", self.disable_file)
                return
            tick_start = time.monotonic()
            self.notify("WATCHDOG=1")
            clk_step = self.clock.check_step()
            if clk_step:
                log.info("wall clock stepped (NTP sync or manual set)")

            self.tick(tick_start, clk_step)

            self.seq += 1
            self.flush()
            now = time.monotonic()
            if now - tick_start > self.args.deadline:
                self.overruns += 1
            target = next_target(tick_start, self.current_cadence(), now)

    def tick(self, tick_start: float, clk_step: bool):
        if self.bot_wrote_recently():
            return                          # the bot's frame is a sample too

        slot = self.run_dir / ("frame-%02d.jpg" % (self.seq % FRAME_RING_SLOTS))
        res = self.capture(slot)
        if res == "busy":
            return                          # bot holds the camera; next tick
        luma = luma_of(slot) if res == "ok" else None
        if luma is None:
            was = self.backoff.delay()
            delay = self.backoff.fail()
            if delay != was:
                log.warning("capture failing (%d consecutive); backing off to "
                            "%.0f s", self.backoff.fails, delay)
            return
        if self.backoff.active:
            log.info("capture recovered after %d failures", self.backoff.fails)
            self.backoff.ok()

        was_dark = self.darkgate.dark
        dark = self.darkgate.update(luma)
        if dark != was_dark:
            if dark:
                log.info("dark (luma %.1f); cadence %.0f s, reader skipped",
                         luma, self.args.dark_interval)
            else:
                log.info("light again (luma %.1f); cadence %.0f s", luma,
                         self.args.interval)
                self.force_detect = True    # scene may have changed overnight

        if dark:
            rec = {"state": "dark", "luma": round(luma, 1)}
            if clk_step:
                rec["clk"] = 1
            self.add_record(rec, tick_start)
            return

        rgb = load_rgb(slot)
        if rgb is None:
            delay = self.backoff.fail()
            log.warning("frame decoded for luma but not fully; backoff %.0f s", delay)
            return

        need_detect = (self.force_detect
                       or not self.boxcache.has_any()
                       or self.reading_n % self.args.detect_every == 0)
        if need_detect:
            try:
                dets = self.reader.detect(rgb)
            except Exception:  # noqa: BLE001 - one bad frame must not kill the loop
                log.warning("detect failed", exc_info=True)
                return
            self.force_detect = False
            if dets:
                self.consec_nodetect = 0
                self.boxcache.add(dets)
            else:
                self.consec_nodetect += 1
                if self.consec_nodetect >= 3:
                    # A stale box must never persist through a scene change.
                    self.boxcache.clear()

        dets = self.boxcache.working()
        tta = 8 if (self.args.tta_probe_every
                    and self.reading_n % self.args.tta_probe_every == 0) else 1
        try:
            pots = self.reader.read_pots(rgb, dets, tta) if dets else []
        except Exception:  # noqa: BLE001
            log.warning("read failed", exc_info=True)
            return
        self.reading_n += 1

        # Immediate re-detect triggers: reading jump, gate flip, blind streak.
        usable = False
        for p in pots:
            side = p["side"]
            if p["ok"]:
                usable = True
                prev = self.last_ml.get(side)
                if prev is not None and abs(p["volume_ml"] - prev) > self.args.jump_ml:
                    self.force_detect = True
                self.last_ml[side] = p["volume_ml"]
            if side in self.last_ok and self.last_ok[side] != p["ok"]:
                self.force_detect = True
            self.last_ok[side] = p["ok"]

        if usable:
            self.consec_unusable = 0
            if self.blind:
                self.blind = False
                log.info("usable readings again; cadence %.0f s", self.args.interval)
        else:
            self.consec_unusable += 1
            if self.consec_unusable == 3:
                self.force_detect = True
            if self.consec_unusable >= self.args.blind_after and not self.blind:
                self.blind = True
                log.info("%d consecutive ticks with no usable reading; cadence "
                         "%.0f s", self.consec_unusable, self.args.dark_interval)

        rec = {"luma": round(luma, 1), "pots": slim_pots(pots)}
        if tta > 1:
            rec["tta"] = tta
        if clk_step:
            rec["clk"] = 1
        self.add_record(rec, tick_start)

        if usable:
            fills = [p["fill_fraction"] for p in pots
                     if p["ok"] and p["fill_fraction"] is not None]
            if fills and self.clock.plausible():
                day = iso_utc(self.clock.stamp(tick_start))[:10]
                if self.retention.decide(max(fills), day):
                    full = {"t": iso_utc(self.clock.stamp(tick_start)),
                            "seq": self.seq, "src": "sampler",
                            "luma": round(luma, 1), "tta": tta, "pots": pots}
                    self.persist_frame(slot, full)


# --------------------------------------------------------------------------

def parse_args(argv=None):
    here = Path(__file__).resolve().parent
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model-dir", default=str(here))
    ap.add_argument("--log", default=None,
                    help="readings JSONL strftime pattern; shared with the bot "
                         "(default: <model-dir>/readings-%%Y-%%m.jsonl)")
    ap.add_argument("--run-dir",
                    default=os.environ.get("RUNTIME_DIRECTORY", "/run/kahvi-sampler"))
    ap.add_argument("--state-dir",
                    default=os.environ.get("STATE_DIRECTORY", "/var/lib/kahvi-sampler"))
    ap.add_argument("--lock", default="/run/lock/kahvicam.lock")
    ap.add_argument("--disable-file", default="/etc/kahvi-sampler/disabled")
    ap.add_argument("--resolution", default="1280x720")
    ap.add_argument("--interval", type=float, default=10.0)
    ap.add_argument("--dark-interval", type=float, default=60.0)
    ap.add_argument("--detect-every", type=int, default=6)
    ap.add_argument("--tta-probe-every", type=int, default=20,
                    help="run TTA=8 on one reading tick in N for burn-in "
                         "comparison; 0 disables")
    ap.add_argument("--flush-sec", type=float, default=60.0)
    ap.add_argument("--ring-mb", type=int, default=500)
    ap.add_argument("--min-free-mb", type=int, default=200)
    ap.add_argument("--jump-ml", type=float, default=300.0)
    ap.add_argument("--blind-after", type=int, default=30)
    ap.add_argument("--deadline", type=float, default=6.0)
    ap.add_argument("--threads", type=int, default=2)
    args = ap.parse_args(argv)
    if args.log is None:
        args.log = str(Path(args.model_dir) / "readings-%Y-%m.jsonl")
    return args


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, stream=sys.stderr,
                        format="%(levelname)s %(message)s")
    sampler = Sampler(parse_args(argv))

    def _term(signum, frame):
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, _term)
    try:
        return sampler.start()
    except SystemExit:
        sampler.flush(force=True)
        raise


if __name__ == "__main__":
    sys.exit(main())
