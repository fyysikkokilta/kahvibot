"""Benchmark: legacy vs streamlined pipeline on this machine, with real frames,
real inference and Pi-anchored virtual time.

    cd coffee_mesh_pred
    python -m gym.bench --quick          # smoke run
    python -m gym.bench                  # full: microbench, equivalence, scenarios, gate sweep
"""
from __future__ import annotations

import os

# numpy's float64 matmuls in read_frame.area_resize oversubscribe OpenBLAS on a
# 20-thread desktop (detect 350 ms -> 40 ms with one BLAS thread); the Pi has no
# such contention, so pin BLAS to one thread for representative relative costs.
for _v in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import argparse
import json
import statistics as st
import subprocess
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
C10 = HERE.parent
ROOT = C10.parent.parent                 # .../coffee
for p in (str(C10), str(C10.parent)):
    if p not in sys.path:
        sys.path.insert(0, p)
from gym.paths import ARCHIVE, COFFEE_ROOT, KAHVIBOT, RESEARCH, WORK  # noqa: E402,F401

from pipeline.gate import Gate                     # noqa: E402
from pipeline.graphing import load_kahvibot_graphs  # noqa: E402
from pipeline.reader import WarmReader, legacy_pots  # noqa: E402
from pipeline.service import ServiceConfig           # noqa: E402
from gym.archive import FrameArchive                 # noqa: E402
from gym.costs import PiCosts                        # noqa: E402
from gym.legacy import run_legacy                    # noqa: E402
from gym.memo import MemoReader                      # noqa: E402
from gym.sim import run_streamlined                  # noqa: E402
from gym import workload                             # noqa: E402

MODEL_DIR = C10 / "models"
ARCHIVE_DIRS = [ARCHIVE, COFFEE_ROOT / "coffee_images" / "data" / "chat_frames"]
READINGS = [COFFEE_ROOT / "kahviraspi_logs_2026-09-09" / "coffee-reader" / f"readings-2026-0{m}.jsonl" for m in (8, 9)]
GRAPHS_PY = KAHVIBOT / "graphs.py"


def fmt(x, nd=1):
    if x is None:
        return "-"
    if isinstance(x, float):
        return f"{x:.{nd}f}"
    return str(x)


# --------------------------------------------------------------------------
# 1. microbenchmarks
# --------------------------------------------------------------------------

def microbench(reader: WarmReader, frames, n_cold: int = 3):
    from pipeline.camera import Frame
    rows = {}
    # cold subprocess: python read_frame.py (TTA=8), as the bot does today
    cold = []
    for f in frames[:n_cold]:
        t0 = time.perf_counter()
        subprocess.run([sys.executable, str(C10 / "read_frame.py"), "--model-dir", str(MODEL_DIR), str(f.path)],
                       capture_output=True, text=True)
        cold.append(time.perf_counter() - t0)
    rows["cold_subprocess_tta8_s"] = st.median(cold)
    # warm
    d, r1, r8, rc = [], [], [], []
    for f in frames:
        rgb = Frame(f.read(), f.epoch, 0.0).rgb()
        dets, dt = reader.detect_timed(rgb)
        d.append(dt)
        _, dt1 = reader.read_pots(rgb, dets, 1)
        r1.append(dt1)
        _, dt8 = reader.read_pots(rgb, dets, 8)
        r8.append(dt8)
    rows["warm_detect_s"] = st.median(d)
    rows["warm_read_tta1_s"] = st.median(r1)
    rows["warm_read_tta8_s"] = st.median(r8)
    rows["warm_detect_plus_tta8_s"] = st.median(d) + st.median(r8)
    rows["warm_detect_plus_tta1_s"] = st.median(d) + st.median(r1)
    return rows


def equivalence(reader: WarmReader, frames):
    """WarmReader + legacy_pots must reproduce read_frame.FrameReader byte-for-byte."""
    import read_frame
    from pipeline.camera import Frame
    ref = read_frame.FrameReader(MODEL_DIR, threads=2, tta_views=8)
    mism = 0
    for f in frames:
        rgb = Frame(f.read(), f.epoch, 0.0).rgb()
        a = ref.read(rgb)
        dets, _ = reader.detect_timed(rgb)
        b, _ = reader.read_pots(rgb, dets, 8)
        b = legacy_pots(b, 0.55)
        if json.dumps(a, sort_keys=True) != json.dumps(b, sort_keys=True):
            mism += 1
    return {"frames": len(frames), "mismatches": mism}


# --------------------------------------------------------------------------
# 2. scenarios
# --------------------------------------------------------------------------

def scenario_windows(archive: FrameArchive, real_days: dict, quick: bool):
    dense = [d for d, _ in archive.densest_days(40)]
    dense_sorted = sorted(dense)
    # pick archive days with plenty of frames for the single-day scenarios
    day_a, day_b = dense[0], dense[1]
    typical = sorted(real_days.items(), key=lambda kv: len(kv[1]))[len(real_days) // 2]
    burst = max(real_days.items(), key=lambda kv: len(kv[1]))
    scen = []
    scen.append(("typical day (%s pattern, %d photos) on %s" % (typical[0], len(typical[1]), day_a),
                 day_a, workload.on_day(typical[1], day_a)))
    scen.append(("burst day (%s pattern, %d photos) on %s" % (burst[0], len(burst[1]), day_b),
                 day_b, workload.on_day(burst[1], day_b)))
    if not quick:
        day_c = dense[2]
        base = datetime(day_c.year, day_c.month, day_c.day).timestamp()
        stress = (workload.poisson(60.0, base + 9 * 3600, base + 17 * 3600, seed=1)
                  + workload.burst(base + 10 * 3600, 40, 5.0)
                  + workload.burst(base + 11.5 * 3600, 20, 3.0))
        scen.append(("stress (synthetic): 1 req/min 09-17, 40 requests 5 s apart at 10:00, "
                     "20 requests 3 s apart at 11:30, on %s" % day_c, day_c, sorted(stress)))
    return scen


def interval_sweep(archive, memo, costs, day, reqs, gate_new, graphs_mod, intervals=(10.0, 20.0, 30.0)):
    """Streamlined service at different sampling intervals: CPU vs reuse vs cadence."""
    from pipeline.camera import ArchiveSource
    t0 = datetime(day.year, day.month, day.day, 6, 0).timestamp()
    t1 = datetime(day.year, day.month, day.day, 22, 0).timestamp()
    reqs = [t for t in reqs if t0 <= t <= t1]
    out = []
    for iv in intervals:
        cfg = ServiceConfig(interval=iv, reuse_max_age=max(15.0, iv * 1.5))
        r = run_streamlined(archive, memo, reqs, t0, t1, costs, gate_new, cfg, graphs_mod,
                            workload.graph_calls(reqs), source=ArchiveSource(archive))
        s = r.summary()
        s["interval"] = iv
        s["reuse_max_age"] = cfg.reuse_max_age
        out.append(s)
    return out


def run_scenarios(archive, memo, costs, scen, gate_new, cfg, graphs_mod, quick):
    from pipeline.camera import ArchiveSource
    out = []
    for title, day, reqs in scen:
        t0 = datetime(day.year, day.month, day.day, 6, 0).timestamp()
        t1 = datetime(day.year, day.month, day.day, 22, 0).timestamp()
        reqs = [t for t in reqs if t0 <= t <= t1]
        gcalls = workload.graph_calls(reqs)
        src = ArchiveSource(archive)
        m0 = memo.misses
        leg = run_legacy(archive, memo, reqs, t0, t1, costs, source=src)
        m1 = memo.misses
        new = run_streamlined(archive, memo, reqs, t0, t1, costs, gate_new, cfg, graphs_mod, gcalls, source=src)
        tta_diff = tta_agreement(leg, new)
        cov = coverage(leg.records, new.records if new.records else [], gate_new)
        out.append({"title": title, "requests": len(reqs), "legacy": leg.summary(), "new": new.summary(),
                    "tta_agreement_ml": tta_diff, "coverage": cov,
                    "memo": {"legacy_misses": m1 - m0, "new_misses": memo.misses - m1}})
        print(f"  done: {title}", flush=True)
    return out


def tta_agreement(leg, new):
    """How much the bot's answer changes when TTA=8 (legacy, fresh detect) is
    replaced by the service's TTA=1 cached-box reading of the same archive frame:
    median and p90 of |ml8 - ml1| per pot, over frames both pipelines read."""
    tta1 = dict(leg.sampler_pots_tta1)
    tta1.update(new.bot_pots)          # frames the new service served to the bot
    d_ml, d_h = [], []
    for ident, pots8 in leg.bot_pots_tta8:
        p1 = {p["side"]: p for p in tta1.get(ident, [])}
        for p8 in pots8:
            q = p1.get(p8["side"])
            if q is None:
                continue
            d_ml.append(abs(p8["ml"] - q["ml"]))
            d_h.append(abs(p8["h"] - q["h"]))
    if not d_ml:
        return None
    d_ml.sort()
    return {"n": len(d_ml), "ml_median": round(st.median(d_ml), 1),
            "ml_p90": round(d_ml[int(0.9 * (len(d_ml) - 1))], 1), "h_median": round(st.median(d_h), 4)}


def coverage(leg_records, new_records, gate_new):
    def cov(records, gate):
        n = ok = 0
        for r in records:
            if "pots" not in r or r.get("src") != "sampler":
                continue
            for p in r["pots"]:
                n += 1
                ok += gate.tier_pot(p) != "abstain"
        return n, ok
    n1, o1 = cov(leg_records, Gate(0.55, 0.55))
    n2, o2 = cov(new_records, gate_new)
    return {"legacy_pots": n1, "legacy_usable_0.55": o1, "new_pots": n2, "new_usable": o2}


# --------------------------------------------------------------------------
# 3. gate sweep over an archive day
# --------------------------------------------------------------------------

def gate_sweep(reader: WarmReader, frames, gates=(0.55, 0.58, 0.60, 0.62, 0.65, 0.70)):
    from pipeline.camera import Frame
    pots_all = []
    for f in frames:
        rgb = Frame(f.read(), f.epoch, 0.0).rgb()
        dets, _ = reader.detect_timed(rgb)
        pots, _ = reader.read_pots(rgb, dets, 1)
        pots_all.extend(pots)
    rows = []
    for g in gates:
        passed = [p for p in pots_all if p["e"] <= g]
        rows.append({"gate": g, "coverage": len(passed) / max(1, len(pots_all)),
                     "n": len(passed), "nonempty_ge_125ml": sum(p["ml"] >= 125 for p in passed)})
    return {"pots": len(pots_all), "rows": rows}


# --------------------------------------------------------------------------
# report
# --------------------------------------------------------------------------

def write_report(path: Path, micro, costs, equiv, scen, sweep, meta, sweep_iv=None):
    L = []
    L.append("# Pipeline benchmark — %s\n" % meta["when"])
    L.append("Machine: %s. Archive frames: %d (%s). Model: %s.\n" % (meta["machine"], meta["frames"], meta["archive_span"], MODEL_DIR))
    L.append("## 1. Microbenchmarks (this machine, median over %d frames)\n" % meta["micro_frames"])
    L.append("| stage | local s | Pi-projected s |\n|---|---|---|")
    for k, v in micro.items():
        proj = v * costs.scale if not k.startswith("cold") else None
        L.append("| %s | %.3f | %s |" % (k, v, fmt(proj, 2)))
    L.append("\nPi scale factor = %.1f local→Pi, anchored on the Pi's measured 8 s detect+TTA8 read. "
             "Cold-start on the Pi is an assumption (%.0f s); fswebcam %.0f s.\n" % (costs.scale, costs.cold_start_s, costs.capture_s))
    L.append("## 2. Numerics\n\nWarmReader + legacy_pots vs read_frame.FrameReader on %d frames: **%d mismatches**.\n"
             % (equiv["frames"], equiv["mismatches"]))
    L.append("## 3. Scenarios (virtual day 06:00–22:00, real frames, real inference)\n")
    for s in scen:
        a, b = s["legacy"], s["new"]
        L.append("### %s\n" % s["title"])
        L.append("| metric | legacy | streamlined |\n|---|---|---|")
        rows = [
            ("requests", a["requests"], b["requests"]),
            ("photo latency p50 (s)", a["photo_latency_p50"], b["photo_latency_p50"]),
            ("photo latency p90 (s)", a["photo_latency_p90"], b["photo_latency_p90"]),
            ("photo latency max (s)", a["photo_latency_max"], b["photo_latency_max"]),
            ("reading latency p50 (s)", a["reading_latency_p50"], b["reading_latency_p50"]),
            ("requests served from a fresh sampler frame", "-", b["requests_reused"]),
            ("camera captures (bot + sampler)", a["captures"], b["captures"]),
            ("sampler lit ticks", a["sampler_lit_ticks"], b["sampler_lit_ticks"]),
            ("sampler cadence median (s)", a["sampler_gap_median"], b["sampler_gap_median"]),
            ("sampler blind hours (legacy rule)", a["blind_hours"], "-"),
            ("Pi CPU-seconds, whole day", a["cpu_total_s"], b["cpu_total_s"]),
            ("records written", a["records"], b["records"]),
            ("/graph calls", "-", b["graph_calls"]),
            ("/graph renders (mtime key vs last-usable key)", b["graph_renders_legacy_key"], b["graph_renders"]),
        ]
        for name, x, y in rows:
            L.append("| %s | %s | %s |" % (name, fmt(x), fmt(y)))
        c = s["coverage"]
        L.append("\nSampler pot readings: legacy %d (usable at 0.55: %d) · streamlined %d (usable at new gate: %d)\n"
                 % (c["legacy_pots"], c["legacy_usable_0.55"], c["new_pots"], c["new_usable"]))
        ta = s.get("tta_agreement_ml")
        if ta:
            L.append("TTA=8 (legacy bot) vs TTA=1 (service) on the same frames, n=%d: median |Δml| %.1f, p90 %.1f, median |Δh| %.4f\n"
                     % (ta["n"], ta["ml_median"], ta["ml_p90"], ta["h_median"]))
    if sweep_iv:
        L.append("## 3b. Streamlined service: sampling interval trade-off (typical day)\n")
        L.append("| interval s | reuse age s | requests reused | photo p50 s | photo p90 s | lit ticks | cadence median s | Pi CPU-s/day | records |\n|---|---|---|---|---|---|---|---|---|")
        for s in sweep_iv:
            L.append("| %.0f | %.0f | %d/%d | %s | %s | %d | %s | %d | %d |" % (
                s["interval"], s["reuse_max_age"], s["requests_reused"], s["requests"],
                fmt(s["photo_latency_p50"]), fmt(s["photo_latency_p90"]), s["sampler_lit_ticks"],
                fmt(s["sampler_gap_median"]), s["cpu_total_s"], s["records"]))
        L.append("")
    L.append("## 4. Gate sweep on %d pot readings from archive frames\n" % sweep["pots"])
    L.append("| gate | coverage | n | of which ≥125 ml |\n|---|---|---|---|")
    for r in sweep["rows"]:
        L.append("| %.2f | %.0f%% | %d | %d |" % (r["gate"], 100 * r["coverage"], r["n"], r["nonempty_ge_125ml"]))
    L.append("\n## 5. Cost model\n\n" + Path(HERE / "costs.py").read_text(encoding="utf-8").split('"""')[1])
    path.write_text("\n".join(L) + "\n", encoding="utf-8")


def main(argv=None) -> int:
    global MODEL_DIR
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--micro-frames", type=int, default=20)
    ap.add_argument("--sweep-frames", type=int, default=400)
    ap.add_argument("--out", default=str(HERE / "BENCH.md"))
    ap.add_argument("--json", default=str(HERE / "bench_results.json"))
    ap.add_argument("--model-dir", default=str(MODEL_DIR), help="ONNX dir (reader, fastbox, calibration, manifest)")
    ap.add_argument("--gate", default="0.62,0.68", help="ok_max,uncertain_max for the streamlined service")
    ap.add_argument("--gate-mode", default="agree", choices=["entropy", "agree"],
                    help="agree = temporal agreement with the previous reading (gym/GATE3_*.md), entropy fallback")
    a = ap.parse_args(argv)
    if a.quick:
        a.micro_frames, a.sweep_frames = 6, 60
    MODEL_DIR = Path(a.model_dir)

    t_start = time.perf_counter()
    archive = FrameArchive(ARCHIVE_DIRS)
    print(f"archive: {len(archive)} frames; densest days: {archive.densest_days(3)}")
    reader = WarmReader(MODEL_DIR, threads=2)
    dense_day = archive.densest_days(1)[0][0]
    day_frames = archive.on_day(dense_day)
    micro_frames = day_frames[:: max(1, len(day_frames) // a.micro_frames)][: a.micro_frames]

    print("microbench...", flush=True)
    micro = microbench(reader, micro_frames, n_cold=2 if a.quick else 3)
    costs = PiCosts().calibrate(micro["warm_detect_plus_tta8_s"])
    print("  ", {k: round(v, 4) for k, v in micro.items()}, "scale", round(costs.scale, 1))

    print("equivalence...", flush=True)
    equiv = equivalence(reader, micro_frames)
    print("  ", equiv)

    real_days = workload.by_day(workload.bot_photo_times(READINGS))
    scen = scenario_windows(archive, real_days, a.quick)
    graphs_mod = load_kahvibot_graphs(GRAPHS_PY) if GRAPHS_PY.is_file() else None
    g_ok, g_unc = (float(x) for x in a.gate.split(","))
    gate_new = Gate(g_ok, g_unc, mode=a.gate_mode)
    cfg = ServiceConfig()
    print("scenarios...", flush=True)
    memo = MemoReader(reader)
    results = run_scenarios(archive, memo, costs, scen, gate_new, cfg, graphs_mod, a.quick)

    print("interval sweep...", flush=True)
    sweep_iv = interval_sweep(archive, memo, costs, scen[0][1], scen[0][2], gate_new, graphs_mod,
                              intervals=(10.0, 30.0) if a.quick else (10.0, 15.0, 20.0, 30.0))

    print("gate sweep...", flush=True)
    sweep_frames = archive.frames[:: max(1, len(archive) // a.sweep_frames)][: a.sweep_frames]
    sweep = gate_sweep(reader, sweep_frames)

    meta = {"when": datetime.now().isoformat(timespec="minutes"), "machine": "i7-12700H, 20 threads, onnxruntime CPU, 2 intra-op threads",
            "frames": len(archive), "archive_span": "%s .. %s" % (datetime.fromtimestamp(archive.epochs[0]).date(), datetime.fromtimestamp(archive.epochs[-1]).date()),
            "micro_frames": len(micro_frames), "elapsed_s": round(time.perf_counter() - t_start)}
    Path(a.json).write_text(json.dumps({"micro": micro, "costs": costs.__dict__, "equivalence": equiv,
                                        "scenarios": results, "interval_sweep": sweep_iv, "sweep": sweep,
                                        "meta": meta}, indent=1, default=str),
                            encoding="utf-8")
    write_report(Path(a.out), micro, costs, equiv, results, sweep, meta, sweep_iv)
    print(f"report -> {a.out}  ({meta['elapsed_s']} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
