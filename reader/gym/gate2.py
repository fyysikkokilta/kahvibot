"""Gate v2: can a small learned score decide "show this reading" better than
`entropy <= 0.55`?

Data: every hand-clicked record (257, Jan-Jun 2026 camera; 158 train / 99 blind
by the frozen hash) plus the field set (31 clicked pots, 2026-09 camera, all
held out). For each, the reader's outputs on the cache box: h, e, d (detector
score), u (usable logit), v (surface logit), plus luma and side. Target: the
reading is "good" if |Δh|·1250 ≤ ERR_OK ml against the human click.

Model: logistic regression on standardised features, fitted by gradient descent
in numpy (no sklearn on this box). Compared to the entropy gate on the same
blind/field records by coverage-vs-error curves: at equal coverage, which gate
keeps the more accurate readings?

    python -m gym.gate2 --model-dir _work/onnx_v8
"""
from __future__ import annotations

import os
for _v in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import argparse
import json
import statistics as st
import sys
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

FULL_ML = 1250.0
FEATS = ("e", "h", "d", "u", "v", "luma", "is_left")


def hand_h(rec):
    return (rec["y_base"] - rec["y_surf"]) / (rec["y_base"] - rec["y_top"])


def collect(reader: WarmReader, meta_path: Path, hand_path: Path, frames_dir: Path, blind_keys: set, era_tag: str):
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    hand = json.loads(hand_path.read_text(encoding="utf-8"))
    by_stem: dict[str, list] = {}
    for r in meta:
        key = f"{r['stem']}__{r['side']}"
        if key in hand and hand[key].get("y_surf") is not None:
            by_stem.setdefault(r["stem"], []).append(r)
    rows = []
    for stem, recs in by_stem.items():
        p = frames_dir / f"{stem}.jpg"
        if not p.exists():
            continue
        fr = Frame(p.read_bytes(), 0.0, 0.0)
        rgb = fr.rgb()
        if rgb is None:
            continue
        luma = fr.luma() or 0.0
        dets = [{"side": r["side"], "box": r["box"], "score": r.get("score", 0.9)} for r in recs]
        pots, _ = reader.read_pots(rgb, dets, 1)
        for pot in pots:
            key = f"{stem}__{pot['side']}"
            hh = hand_h(hand[key])
            rows.append({"key": key, "set": era_tag, "blind": key in blind_keys,
                         "e": pot["e"], "h": pot["h"], "d": pot["d"], "u": pot["u"], "v": pot["v"],
                         "luma": luma, "is_left": 1.0 if pot["side"] == "left" else 0.0,
                         "err_ml": abs(pot["h"] - hh) * FULL_ML, "human_h": hh})
    return rows


def fit_logreg(X, y, l2=1e-2, steps=3000, lr=0.1):
    mu, sd = X.mean(0), X.std(0) + 1e-6
    Z = (X - mu) / sd
    w = np.zeros(Z.shape[1]); b = 0.0
    for _ in range(steps):
        p = 1 / (1 + np.exp(-(Z @ w + b)))
        g = p - y
        w -= lr * (Z.T @ g / len(y) + l2 * w)
        b -= lr * g.mean()
    return {"w": w, "b": b, "mu": mu, "sd": sd}


def score(model, X):
    Z = (X - model["mu"]) / model["sd"]
    return 1 / (1 + np.exp(-(Z @ model["w"] + model["b"])))


def curve(order_score, err, coverages=(0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0)):
    """Keep the top-k by score; report median error of the kept set at each coverage."""
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
    ap.add_argument("--err-ok", type=float, default=40.0, help="ml; a reading within this is 'good'")
    ap.add_argument("--out", default=str(HERE / "GATE2.md"))
    a = ap.parse_args(argv)
    reader = WarmReader(Path(a.model_dir), threads=4)
    blind = set(json.loads((WORK / "hand_blind.json").read_text(encoding="utf-8"))["keys"])
    rows = collect(reader, WORK / "crops_meta.json", WORK / "hand_lines_clean.json",
                   ARCHIVE, blind, "archive")
    fblind = set(json.loads((WORK / "hand_blind_field.json").read_text(encoding="utf-8"))["keys"])
    field = collect(reader, WORK / "field_meta.json", WORK / "hand_lines_field.json",
                    WORK / "field_frames", fblind, "field")
    for r in field:
        r["blind"] = True                    # field is evaluation-only
    allrows = rows + field
    print(f"archive records {len(rows)} (train {sum(not r['blind'] for r in rows)}, blind {sum(r['blind'] for r in rows)}); field {len(field)}")

    def XY(rs):
        X = np.array([[r[f] for f in FEATS] for r in rs], dtype=np.float64)
        y = np.array([1.0 if r["err_ml"] <= a.err_ok else 0.0 for r in rs])
        e = np.array([r["err_ml"] for r in rs])
        return X, y, e

    train = [r for r in rows if not r["blind"]]
    Xt, yt, _ = XY(train)
    model = fit_logreg(Xt, yt)
    weights = dict(zip(FEATS, [round(float(x), 3) for x in model["w"]]))
    print("weights (standardised):", weights)

    L = ["# Gate v2 — learned reliability score vs entropy gate\n",
         "Model dir: %s. 'Good' = |Δh|·1250 ≤ %.0f ml vs the human click. Logistic regression on %s, "
         "fitted on %d archive-era train records; evaluated on %d blind archive records and %d field pots.\n"
         % (a.model_dir, a.err_ok, ", ".join(FEATS), len(train), sum(r['blind'] for r in rows), len(field)),
         "Standardised weights: `%s`\n" % json.dumps(weights)]
    results = {"weights": weights}
    for name, rs in (("blind archive (Jan–Jun 2026 camera)", [r for r in rows if r["blind"]]),
                     ("blind archive, non-empty only (human h ≥ 0.1)", [r for r in rows if r["blind"] and r["human_h"] >= 0.1]),
                     ("field (2026-09 camera, survey clicks)", field),
                     ("field, non-empty only (human h ≥ 0.1)", [r for r in field if r["human_h"] >= 0.1])):
        if len(rs) < 5:
            continue
        X, y, err = XY(rs)
        s_learned = score(model, X)
        s_entropy = -X[:, FEATS.index("e")]
        s_surface = X[:, FEATS.index("v")]
        cov_e = curve(s_entropy, err)
        cov_l = curve(s_learned, err)
        cov_v = curve(s_surface, err)
        # what the deployed threshold does on this set
        kept = err[X[:, 0] <= 0.55]
        rej = err[X[:, 0] > 0.55]
        L.append("## %s (n=%d)\n" % (name, len(rs)))
        L.append("Deployed gate e ≤ 0.55 keeps %d/%d: kept median err %s ml, rejected median err %s ml. "
                 "All readings: median %.1f ml, %.0f%% within 40 ml.\n"
                 % (len(kept), len(rs), "%.1f" % np.median(kept) if len(kept) else "-",
                    "%.1f" % np.median(rej) if len(rej) else "-", float(np.median(err)), 100 * float(np.mean(err <= 40))))
        L.append("| coverage | entropy gate: median err / ≤40 ml | surface logit: median err / ≤40 ml | learned: median err / ≤40 ml |\n|---|---|---|---|")
        for (c, me, fe), (_, mv, fv), (_, ml_, fl) in zip(cov_e, cov_v, cov_l):
            L.append("| %.0f%% | %.1f / %.0f%% | %.1f / %.0f%% | %.1f / %.0f%% |" % (100 * c, me, 100 * fe, mv, 100 * fv, ml_, 100 * fl))
        L.append("")
        results[name] = {"n": len(rs), "entropy": cov_e, "learned": cov_l, "surface": cov_v,
                         "kept_055": len(kept), "kept_err": float(np.median(kept)) if len(kept) else None,
                         "rej_err": float(np.median(rej)) if len(rej) else None}
    Path(a.out).write_text("\n".join(L) + "\n", encoding="utf-8")
    Path(a.out).with_suffix(".json").write_text(json.dumps(results, indent=1, default=float), encoding="utf-8")
    print("->", a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
