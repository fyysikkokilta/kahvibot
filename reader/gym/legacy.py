"""Discrete-event model of the deployed pipeline (kahvibot + sampler.py), using
real frames and real inference for the numbers and the Pi cost model for time.
Bot and sampler are independent processes, so their timelines are tracked
explicitly and only interact through the camera lock and the 8-second
"bot wrote recently" skip rule, exactly as deployed.

Bot (kahvibot, PTB dispatcher = one handler at a time):
  request -> wait for previous handler -> flock(-w 5) -> fswebcam (2 s)
          -> cold read_frame.py subprocess (cold start + detect + TTA=8 read)
          -> send. Latency = end - request. Record appended (src=bot).
Sampler (sampler.py under CPUQuota=25 %):
  tick every 10 s lit / 60 s dark or blind; skip if the bot wrote < 8 s ago or
  holds the camera; lit tick wall 23 s (measured), TTA=8 probe every 20 readings
  (96 s), detect every 6; blind after 30 consecutive ticks with no ok reading at
  gate 0.55 (the deployed rule).
"""
from __future__ import annotations

import statistics as st
from dataclasses import dataclass, field

from pipeline.camera import ArchiveSource
from pipeline.gate import Gate
from pipeline.service import BoxCache, DarkGate
from pipeline.store import iso_utc, slim

LEGACY_GATE = Gate(0.55, 0.55)


@dataclass
class LegacyResult:
    requests: int = 0
    latency: list = field(default_factory=list)
    bot_captures: int = 0
    sampler_ticks: int = 0
    sampler_lit_ticks: int = 0
    sampler_skipped: int = 0
    sampler_dark_ticks: int = 0
    sampler_probe_ticks: int = 0
    sampler_gaps: list = field(default_factory=list)
    blind_seconds: float = 0.0
    cpu_bot_s: float = 0.0
    cpu_sampler_s: float = 0.0
    compute_local_s: float = 0.0
    records: list = field(default_factory=list)
    bot_pots_tta8: list = field(default_factory=list)   # (ident, pots)
    sampler_pots_tta1: dict = field(default_factory=dict)  # ident -> pots

    def summary(self):
        lat = sorted(self.latency)
        q = lambda p: lat[min(len(lat) - 1, int(p * len(lat)))] if lat else None
        gaps = sorted(self.sampler_gaps)
        return {
            "requests": self.requests,
            "photo_latency_p50": q(0.5), "photo_latency_p90": q(0.9),
            "photo_latency_max": lat[-1] if lat else None,
            "reading_latency_p50": q(0.5), "reading_latency_p90": q(0.9),
            "requests_reused": 0, "requests_captured": self.requests,
            "captures": self.bot_captures + self.sampler_lit_ticks + self.sampler_dark_ticks,
            "bot_captures": self.bot_captures,
            "sampler_lit_ticks": self.sampler_lit_ticks,
            "sampler_skipped": self.sampler_skipped,
            "sampler_gap_median": st.median(gaps) if gaps else None,
            "sampler_gap_p90": gaps[min(len(gaps) - 1, int(0.9 * len(gaps)))] if gaps else None,
            "blind_hours": round(self.blind_seconds / 3600, 2),
            "cpu_bot_s": round(self.cpu_bot_s), "cpu_sampler_s": round(self.cpu_sampler_s),
            "cpu_total_s": round(self.cpu_bot_s + self.cpu_sampler_s),
            "records": len(self.records),
        }


def run_legacy(archive, reader, requests: list[float], t0: float, t1: float, costs,
               source: ArchiveSource | None = None) -> LegacyResult:
    src = source or ArchiveSource(archive)
    res = LegacyResult()
    dark = DarkGate()
    boxes = BoxCache()
    st_ = {"reading_n": 0, "force_detect": True}
    consec_unusable = 0
    blind = False
    blind_since = None
    seq = 0
    bot_free = t0
    bot_last_write = -1e18
    bot_cap = (-1e18, -1e18)
    sampler_cap = (-1e18, -1e18)
    next_tick = t0
    last_lit_tick = None
    reqs = sorted(requests)
    ri = 0

    def read_frame(fr, tta, force):
        """Detect (per rule) + read. Returns (pots, local_seconds)."""
        rgb = fr.rgb()
        if rgb is None:
            return None, 0.0
        total = 0.0
        need = force or st_["force_detect"] or not boxes.has_any() or st_["reading_n"] % 6 == 0
        if need:
            dets, dt = reader.detect_timed(rgb, ident=fr.ident)
            total += dt
            st_["force_detect"] = False
            if dets:
                boxes.add(dets)
        dets = boxes.working()
        pots, dt = reader.read_pots(rgb, dets, tta, ident=fr.ident) if dets else ([], 0.0)
        total += dt
        st_["reading_n"] += 1
        LEGACY_GATE.apply(pots)
        res.compute_local_s += total
        return pots, total

    def record(fr, luma, pots, src_name, tta):
        nonlocal seq
        rec = {"t": iso_utc(fr.captured_wall), "seq": seq, "src": src_name,
               "luma": round(luma, 1), "pots": slim(pots)}
        if tta > 1:
            rec["tta"] = tta
        res.records.append(rec)
        seq += 1

    while True:
        next_req = reqs[ri] if ri < len(reqs) else None
        if next_req is None and next_tick > t1:
            break
        if next_req is not None and next_req <= next_tick:
            # ---- bot handler (own process; only the camera lock couples it) -----
            ri += 1
            start = max(next_req, bot_free)
            if sampler_cap[0] <= start < sampler_cap[1]:
                start = min(sampler_cap[1], start + 5.0)          # flock -w 5
            cap_end = start + costs.capture_s
            fr = src.frame_at(start, start - t0)
            res.bot_captures += 1
            luma = fr.luma() or 0.0
            pots, dt_local = read_frame(fr, 8, True)             # fresh detect, TTA=8
            pots = pots or []
            end = cap_end + costs.cold_start_s + dt_local * costs.scale + costs.bot_upload_s
            res.requests += 1
            res.latency.append(end - next_req)              # photo delivered
            res.cpu_bot_s += costs.capture_cpu_s + costs.cold_start_s + dt_local * costs.scale
            record(fr, luma, pots, "bot", 8)
            res.bot_pots_tta8.append((fr.ident, [dict(p) for p in pots]))
            bot_free = end
            bot_last_write = end
            bot_cap = (start, cap_end)
            continue
        # ---- sampler tick -------------------------------------------------------
        s = next_tick
        res.sampler_ticks += 1
        cadence = 60.0 if (dark.dark or blind) else 10.0
        if 0.0 <= s - bot_last_write < 8.0 or bot_cap[0] <= s < bot_cap[1]:
            res.sampler_skipped += 1
            next_tick = s + cadence
            continue
        fr = src.frame_at(s, s - t0)
        sampler_cap = (s, s + costs.capture_s)
        luma = fr.luma()
        if luma is None:
            next_tick = s + cadence
            continue
        was_dark = dark.dark
        if dark.update(luma):
            res.sampler_dark_ticks += 1
            res.cpu_sampler_s += costs.legacy_dark_tick_cpu_s()
            res.records.append({"t": iso_utc(fr.captured_wall), "seq": seq, "src": "sampler",
                                "state": "dark", "luma": round(luma, 1)})
            seq += 1
            next_tick = s + max(60.0, costs.legacy_dark_tick_wall_s)
            continue
        if was_dark:
            st_["force_detect"] = True
        probe = st_["reading_n"] % 20 == 0
        pots, _ = read_frame(fr, 8 if probe else 1, False)
        if pots is None:
            next_tick = s + cadence
            continue
        res.sampler_lit_ticks += 1
        if probe:
            res.sampler_probe_ticks += 1
        else:
            res.sampler_pots_tta1.setdefault(fr.ident, [dict(p) for p in pots])
        wall = costs.legacy_probe_wall_s if probe else costs.legacy_tick_wall_s
        res.cpu_sampler_s += costs.legacy_probe_cpu_s() if probe else costs.legacy_tick_cpu_s()
        usable = any(p["ok"] for p in pots)
        if usable:
            consec_unusable = 0
            if blind:
                blind = False
                res.blind_seconds += s - blind_since
        else:
            consec_unusable += 1
            if consec_unusable >= 30 and not blind:
                blind, blind_since = True, s
        record(fr, luma, pots, "sampler", 8 if probe else 1)
        if last_lit_tick is not None:
            res.sampler_gaps.append(s - last_lit_tick)
        last_lit_tick = s
        cadence = 60.0 if blind else 10.0
        next_tick = s + wall + cadence          # overrun rule: target passed -> now + cadence
    if blind and blind_since is not None:
        res.blind_seconds += t1 - blind_since
    return res
