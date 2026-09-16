"""Gate v3: temporal agreement as the reliability signal.

The streamlined sampler reads every ~10 s, so every reading has neighbours.
If a reading agrees with the readings just before and after it, the surface
was found consistently; if it jumps, something (a hand, glare, a pour) was in
the way. Unlike entropy this needs no model change, and unlike a learned gate
it needs no labels. Question: on the blind hand-clicked records, does the
neighbour spread order errors better than entropy does?

The archive has one frame per ~5 min, so "neighbours" here are the nearest
archive frames within ±NEIGHBOUR_MAX_S — a harsher test than 10 s neighbours,
because coffee can actually change in five minutes.

    python -m gym.gate3_temporal --model-dir _work/onnx_v8
"""
from __future__ import annotations

import os
for _v in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import argparse
import json
import statistics as st
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
C10 = HERE.parent
REPO = C10.parent
for p in (str(C10), str(REPO)):
    if p not in sys.path:
        sys.path.insert(0, p)
from gym.paths import ARCHIVE, COFFEE_ROOT, KAHVIBOT, RESEARCH, WORK  # noqa: E402,F401

from pipeline.camera import Frame          # noqa: E402
from pipeline.reader import WarmReader     # noqa: E402
from gym.archive import FrameArchive       # noqa: E402

FULL_ML = 1250.0
NEIGHBOUR_MAX_S = 12 * 60


def hand_h(rec):
    return (rec["y_base"] - rec["y_surf"]) / (rec["y_base"] - rec["y_top"])


def curve(order_score, err, coverages=(0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0)):
    idx = np.argsort(-order_score)
    out = []
    for c in coverages:
        k = max(1, int(round(c * len(err))))
        kept = err[idx[:k]]
        out.append((c, float(np.median(kept)), float(np.mean(kept <= 40.0))))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model-dir", default=str(WORK / "onnx_v8"))
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    tag = Path(a.model_dir).name.replace("onnx_", "")
    out_path = Path(a.out or HERE / f"GATE3_{tag}.md")
    reader = WarmReader(Path(a.model_dir), threads=2)
    archive = FrameArchive([ARCHIVE])
    meta = json.loads((WORK / "crops_meta.json").read_text(encoding="utf-8"))
    hand = json.loads((WORK / "hand_lines_clean.json").read_text(encoding="utf-8"))
    blind = set(json.loads((WORK / "hand_blind.json").read_text(encoding="utf-8"))["keys"])
    by_key = {f"{r['stem']}__{r['side']}": r for r in meta}
    rows = []
    cache: dict[str, dict] = {}       # stem -> {side: pot}

    def read_stem(stem, box_by_side):
        if stem in cache:
            return cache[stem]
        p = ARCHIVE / f"{stem}.jpg"
        if not p.exists():
            cache[stem] = {}
            return {}
        rgb = Frame(p.read_bytes(), 0.0, 0.0).rgb()
        if rgb is None:
            cache[stem] = {}
            return {}
        if box_by_side:
            dets = [{"side": s, "box": b, "score": 0.9} for s, b in box_by_side.items()]
        else:
            dets, _ = reader.detect_timed(rgb)
        pots, _ = reader.read_pots(rgb, dets, 1)
        cache[stem] = {q["side"]: q for q in pots}
        return cache[stem]

    for key in sorted(blind):
        rec = hand.get(key)
        r = by_key.get(key)
        if not rec or rec.get("y_surf") is None or r is None:
            continue
        stem, side = r["stem"], r["side"]
        pots = read_stem(stem, {side: r["box"]})
        pot = pots.get(side)
        if pot is None:
            continue
        # neighbours: nearest archive frames before and after, within the window
        t0 = datetime.strptime(stem[-19:], "%Y-%m-%d_%H-%M-%S").timestamp()
        import bisect
        i = bisect.bisect_left(archive.epochs, t0)
        neigh = []
        for j in (i - 1, i + 1):
            if 0 <= j < len(archive.frames) and abs(archive.frames[j].epoch - t0) <= NEIGHBOUR_MAX_S and archive.frames[j].stem != stem[-19:]:
                q = read_stem(archive.frames[j].path.stem, None).get(side)
                if q is not None:
                    neigh.append(q["h"])
        if not neigh:
            continue
        hs = [pot["h"]] + neigh
        rows.append({"key": key, "h": pot["h"], "e": pot["e"], "n_neigh": len(neigh),
                     "spread_ml": (max(hs) - min(hs)) * FULL_ML,
                     "nearest_ml": min(abs(pot["h"] - x) for x in neigh) * FULL_ML,
                     "err_ml": abs(pot["h"] - hand_h(rec)) * FULL_ML, "human_h": hand_h(rec)})
    print(f"blind records with neighbours: {len(rows)}")
    L = ["# Gate v3 — temporal agreement vs entropy (%s)\n" % tag,
         "Blind hand-clicked records whose archive neighbours (±%d min) exist: %d. Error = |Δh|·1250 ml vs the click. "
         "Ordering by neighbour spread (smaller = more consistent) vs by entropy (smaller = sharper).\n" % (NEIGHBOUR_MAX_S // 60, len(rows))]
    results = {}
    for name, rs in (("all", rows), ("non-empty (human h ≥ 0.1)", [r for r in rows if r["human_h"] >= 0.1])):
        if len(rs) < 5:
            continue
        err = np.array([r["err_ml"] for r in rs])
        c_e = curve(-np.array([r["e"] for r in rs]), err)
        c_s = curve(-np.array([r["spread_ml"] for r in rs]), err)
        c_n = curve(-np.array([r["nearest_ml"] for r in rs]), err)
        L.append("## %s (n=%d) — all readings: median %.1f ml, %.0f%% within 40 ml\n" % (name, len(rs), float(np.median(err)), 100 * float(np.mean(err <= 40))))
        L.append("| coverage | entropy: median err / ≤40 ml | neighbour spread: median err / ≤40 ml | nearest neighbour |Δ|: median err / ≤40 ml |\n|---|---|---|---|")
        for (c, me, fe), (_, ms, fs), (_, mn, fn) in zip(c_e, c_s, c_n):
            L.append("| %.0f%% | %.1f / %.0f%% | %.1f / %.0f%% | %.1f / %.0f%% |" % (100 * c, me, 100 * fe, ms, 100 * fs, mn, 100 * fn))
        L.append("")
        results[name] = {"n": len(rs), "entropy": c_e, "spread": c_s, "nearest": c_n,
                         "spread_median_ml": float(np.median([r["spread_ml"] for r in rs]))}
    out_path.write_text("\n".join(L) + "\n", encoding="utf-8")
    out_path.with_suffix(".json").write_text(json.dumps(results, indent=1), encoding="utf-8")
    print("->", out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
