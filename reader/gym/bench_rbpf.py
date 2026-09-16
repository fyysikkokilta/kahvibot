"""Does using the row distribution beat the point estimate plus a gate?

Three questions, answered on real frames:

1. **Accuracy.** Against the 99 frozen blind hand clicks, is the posterior mean
   under the network's own row distribution better than its soft-argmax?
2. **Reliability.** Entropy was shown not to order errors (gym/GATE2, GATE3).
   Does the posterior's standard deviation order them? If it does, the gate is
   replaced by a calibrated uncertainty and nothing has to be thrown away.
3. **Dynamics.** Replayed over a real day of frames, does the filter remove the
   physically impossible level rises the raw reader produces?

    cd reader && python -m gym.bench_rbpf --model-dir ../../coffee_mesh_pred/_work/onnx_v8_logits
"""
from __future__ import annotations

import os

for _v in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import argparse  # noqa: E402
import bisect  # noqa: E402
import json  # noqa: E402
import statistics as st  # noqa: E402
import sys  # noqa: E402
from datetime import datetime  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402

HERE = Path(__file__).resolve().parent
READER = HERE.parent
for p in (str(READER),):
    if p not in sys.path:
        sys.path.insert(0, p)

from gym.archive import FrameArchive  # noqa: E402
from gym.paths import ARCHIVE, WORK  # noqa: E402
from pipeline.camera import Frame  # noqa: E402
from pipeline.rbpf import Calibration, PotRBPF  # noqa: E402
from pipeline.reader import WarmReader, surf_loglik  # noqa: E402

FULL_ML = 1250.0
GRID = np.linspace(0.0, 1.02, 512)


def hand_h(rec):
    return (rec["y_base"] - rec["y_surf"]) / (rec["y_base"] - rec["y_top"])


def frame_posterior(rd, cal, surface_logit=None, outlier=0.02):
    """Single-frame posterior over volume under a flat prior.

    Returns several summaries because they behave very differently here. The
    mean is the wrong point estimate for this posterior: the robust mixture puts
    a uniform pedestal under everything, which drags the mean toward mid-scale,
    and on a bimodal frame the mean lands between the two candidate surfaces,
    the one place the surface certainly is not. The mode is the like-for-like
    comparison against a soft-argmax. Inside the filter the pedestal is correct
    and harmless, because the dynamics supply the prior that anchors it.
    """
    ll = surf_loglik(rd, GRID)
    pi = 1.0 / (1.0 + np.exp(-surface_logit)) if surface_logit is not None else 0.9
    pi = min(max(float(pi), outlier), 1.0 - outlier)
    flat = -np.log(rd["n"])
    m = np.maximum(ll, flat)
    mixed = m + np.log(pi * np.exp(ll - m) + (1.0 - pi) * np.exp(flat - m))
    ml = cal.ml(GRID)

    def summarise(logp):
        w = np.exp(logp - logp.max())
        w = w / w.sum()
        mean = float((w * ml).sum())
        sd = float(np.sqrt((w * (ml - mean) ** 2).sum()))
        order = np.argsort(ml)
        cdf = np.cumsum(w[order])
        median = float(ml[order][int(np.searchsorted(cdf, 0.5).clip(0, len(ml) - 1))])
        return mean, sd, median, float(ml[int(np.argmax(logp))])

    mean, sd, median, mode = summarise(mixed)
    _, sd_pure, _, mode_pure = summarise(ll)
    return {"mean": mean, "sd": sd, "median": median, "mode": mode,
            "sd_pure": sd_pure, "mode_pure": mode_pure}


def coverage_table(score, err, label, coverages=(0.2, 0.4, 0.6, 0.8, 1.0)):
    """Median error of the best-scoring fraction. `score` is higher-is-better."""
    idx = np.argsort(-np.asarray(score))
    out = []
    for c in coverages:
        k = max(1, int(round(c * len(err))))
        kept = np.asarray(err)[idx[:k]]
        out.append((c, float(np.median(kept)), float(np.mean(kept <= 40.0))))
    return label, out


def run_blind(reader, cal, limit=None):
    meta = json.loads((WORK / "crops_meta.json").read_text(encoding="utf-8"))
    hand = json.loads((WORK / "hand_lines_clean.json").read_text(encoding="utf-8"))
    blind = set(json.loads((WORK / "hand_blind.json").read_text(encoding="utf-8"))["keys"])
    by_key = {f"{r['stem']}__{r['side']}": r for r in meta}
    rows = []
    keys = sorted(blind)
    if limit:
        keys = keys[:limit]
    for key in keys:
        rec, r = hand.get(key), by_key.get(key)
        if not rec or rec.get("y_surf") is None or r is None:
            continue
        path = ARCHIVE / f"{r['stem']}.jpg"
        if not path.exists():
            continue
        rgb = Frame(path.read_bytes(), 0.0, 0.0).rgb()
        if rgb is None:
            continue
        dets = [{"side": r["side"], "box": r["box"], "score": 0.9}]
        pots, _ = reader.read_pots(rgb, dets, 1, with_rows=True)
        if not pots or "rowdist" not in pots[0]:
            continue
        q = pots[0]
        truth = cal.ml(hand_h(rec))
        point = cal.ml(q["h"])
        fp = frame_posterior(q["rowdist"], cal, q.get("v"))
        rows.append({"key": key, "truth": truth, "point": point,
                     "post": fp["mean"], "median": fp["median"], "mode": fp["mode"],
                     "sd": fp["sd"], "sd_pure": fp["sd_pure"],
                     "e": q["e"], "v": q.get("v"), "human_h": hand_h(rec)})
    return rows


def run_sequence(reader, cal, days=2, particles=1500):
    """Replay whole days of archived frames and count impossible rises.

    The archive has no plug data, so brewing is latent here - the hardest case.
    A rise is only credible if the filter can also believe a brew happened.
    """
    archive = FrameArchive([ARCHIVE])
    out = []
    for day, _n in archive.densest_days(days):
        # densest_days keys on local dates, so select the same way
        frames = sorted((f for f in archive.frames
                         if datetime.fromtimestamp(f.epoch).date() == day),
                        key=lambda f: f.epoch)
        if len(frames) < 20:
            continue
        filters = {s: PotRBPF(cal, n_particles=particles, seed=hash(s) % 1000) for s in ("left", "right")}
        raw = {"left": [], "right": []}
        filt = {"left": [], "right": []}
        prev_t = None
        for f in frames:
            rgb = Frame(f.path.read_bytes(), 0.0, 0.0).rgb()
            if rgb is None:
                continue
            dets, _ = reader.detect_timed(rgb)
            pots, _ = reader.read_pots(rgb, dets, 1, with_rows=True)
            dt = 0.0 if prev_t is None else max(f.epoch - prev_t, 0.0)
            prev_t = f.epoch
            seen = {q["side"]: q for q in pots}
            for side, filt_obj in filters.items():
                q = seen.get(side)
                post = filt_obj.step(dt=dt, power_w=None,
                                     rowdist=q.get("rowdist") if q else None,
                                     surface_logit=q.get("v") if q else None)
                filt[side].append(post.ml_mean)
                raw[side].append(cal.ml(q["h"]) if q else np.nan)
        for side in ("left", "right"):
            out.append({"day": str(day), "side": side,
                        "raw": np.asarray(raw[side], dtype=float),
                        "filt": np.asarray(filt[side], dtype=float)})
    return out


def step_stats(series, rise_ml=40.0):
    d = np.diff(series[~np.isnan(series)]) if np.isnan(series).any() else np.diff(series)
    if len(d) == 0:
        return {"n": 0, "rises": 0, "falls": 0, "jitter": float("nan")}
    return {"n": len(d), "rises": int(np.sum(d > rise_ml)), "falls": int(np.sum(d < -rise_ml)),
            "jitter": float(1.4826 * np.median(np.abs(d - np.median(d))))}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model-dir", default=str(WORK / "onnx_v8_logits"))
    ap.add_argument("--out", default=str(HERE / "RBPF.md"))
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--days", type=int, default=2)
    ap.add_argument("--particles", type=int, default=1500)
    ap.add_argument("--skip-sequence", action="store_true")
    a = ap.parse_args(argv)

    model_dir = Path(a.model_dir)
    reader = WarmReader(model_dir, threads=2)
    if "line_logits" not in reader.out_names:
        print("model bundle has no line_logits; re-export with coffee10.export_onnx")
        return 2
    cal = Calibration(model_dir / "calibration.json")

    rows = run_blind(reader, cal, a.limit)
    n = len(rows)
    print(f"blind records scored: {n}")
    err_point = np.array([abs(r["point"] - r["truth"]) for r in rows])
    err_post = np.array([abs(r["post"] - r["truth"]) for r in rows])
    err_med = np.array([abs(r["median"] - r["truth"]) for r in rows])
    err_mode = np.array([abs(r["mode"] - r["truth"]) for r in rows])
    nz = [i for i, r in enumerate(rows) if r["human_h"] >= 0.1]

    L = ["# Row-distribution filter vs point estimate + gate\n",
         f"Model `{model_dir.name}`. Blind set: {n} frozen hand-clicked pot-views "
         f"({len(nz)} non-empty). Error is |estimate - click| in ml; a single click "
         "carries ~21 ml of noise, so differences under ~10 ml are not differences.\n",
         "## 1. Accuracy: soft-argmax vs posterior mean\n",
         "| set | soft-argmax (deployed) | posterior mode | posterior median | posterior mean |",
         "|---|---|---|---|---|",
         f"| all (n={n}) | {np.median(err_point):.1f} | {np.median(err_mode):.1f} | "
         f"{np.median(err_med):.1f} | {np.median(err_post):.1f} |",
         f"| non-empty (n={len(nz)}) | {np.median(err_point[nz]):.1f} | {np.median(err_mode[nz]):.1f} | "
         f"{np.median(err_med[nz]):.1f} | {np.median(err_post[nz]):.1f} |",
         "",
         "The mean is included to show why it must not be the published number: the robust "
         "mixture's uniform pedestal pulls it toward mid-scale, and on a bimodal frame it "
         "lands between the two candidate surfaces. The mode is the like-for-like comparison "
         "with a soft-argmax.\n"]

    L.append("## 2. Reliability: does the posterior's own spread order errors?\n")
    L.append("Keeping only the best-scoring fraction of readings. Entropy was the deployed "
             "gate's signal; posterior sd is what replaces it.\n")
    for name, sel in (("all", list(range(n))), ("non-empty", nz)):
        if len(sel) < 10:
            continue
        e = err_mode[sel]
        by_ent = coverage_table([-rows[i]["e"] for i in sel], e, "entropy")
        by_sd = coverage_table([-rows[i]["sd"] for i in sel], e, "posterior sd")
        L.append(f"### {name} (n={len(sel)})\n")
        L.append("| kept | by entropy: median err / within 40 ml | by posterior sd: median err / within 40 ml |")
        L.append("|---|---|---|")
        for (c, me, fe), (_, ms, fs) in zip(by_ent[1], by_sd[1]):
            L.append(f"| {100*c:.0f}% | {me:.1f} / {100*fe:.0f}% | {ms:.1f} / {100*fs:.0f}% |")
        L.append("")

    if not a.skip_sequence:
        print("replaying archived days...")
        seqs = run_sequence(reader, cal, a.days, a.particles)
        L.append("## 3. Dynamics: impossible rises over a replayed day\n")
        L.append("Only a brew can raise the level. Every other rise is the reader flipping "
                 "between surfaces. No plug data exists for the archive, so the filter has to "
                 "infer brewing here - the hardest case for it.\n")
        L.append("| day | pot | steps | raw rises >40 ml | filtered rises | raw falls | filtered falls | raw jitter | filtered jitter |")
        L.append("|---|---|---|---|---|---|---|---|---|")
        tot_raw = tot_filt = 0
        for s in seqs:
            r, f = step_stats(s["raw"]), step_stats(s["filt"])
            tot_raw += r["rises"]
            tot_filt += f["rises"]
            L.append(f"| {s['day']} | {s['side']} | {r['n']} | {r['rises']} | {f['rises']} | "
                     f"{r['falls']} | {f['falls']} | {r['jitter']:.0f} ml | {f['jitter']:.0f} ml |")
        L.append("")
        L.append(f"Total rises over 40 ml: **{tot_raw} raw -> {tot_filt} filtered**.\n")

    L.append("## 4. What this means for the gate\n")
    L.append("The gate accepted or rejected a frame on entropy and published nothing when it "
             "rejected, which cost ~70 % of readings. The filter publishes every tick with an "
             "interval attached: a diffuse frame widens the posterior instead of deleting it, "
             "and a bimodal frame keeps both surfaces alive until the dynamics or the plug "
             "choose. Coverage becomes 100 % by construction; the honest quantity to show a "
             "user is the interval, not a pass/fail flag.\n")

    Path(a.out).write_text("\n".join(L) + "\n", encoding="utf-8")
    json.dump({"n": n, "median_point": float(np.median(err_point)),
               "median_post": float(np.median(err_post)),
               "rows": [{k: (float(v) if isinstance(v, (int, float, np.floating)) else v)
                         for k, v in r.items()} for r in rows]},
              open(Path(a.out).with_suffix(".json"), "w"), indent=1)
    print("->", a.out)
    print(f"median error: soft-argmax {np.median(err_point):.1f} ml, posterior mean {np.median(err_post):.1f} ml")
    return 0


if __name__ == "__main__":
    sys.exit(main())
