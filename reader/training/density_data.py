"""Cache (frozen-v8 row logits, clicked surface row) pairs for the density head.

The reader's row head was trained with its loss on the soft-argmax, so the shape
of its softmax was never supervised and is not a calibrated density: read as a
likelihood it is measurably worse than the point estimate it produces. This
extracts the inputs needed to fit a small head that *is* supervised as a density,
on top of the frozen network.

    python -m coffee10.density_data              # writes _work/density_ds.npz
"""
from __future__ import annotations

import os

for _v in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import argparse  # noqa: E402
import json  # noqa: E402
import sys  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
READER = REPO.parent / "kahvibot" / "reader"
for p in (str(READER), str(REPO)):
    if p not in sys.path:
        sys.path.insert(0, p)

from pipeline.camera import Frame  # noqa: E402
from pipeline.reader import WarmReader  # noqa: E402

WORK = REPO / "_work"
ARCHIVE = REPO / "raw_img"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model-dir", default=str(WORK / "onnx_v8_logits"))
    ap.add_argument("--out", default=str(WORK / "density_ds.npz"))
    a = ap.parse_args(argv)

    reader = WarmReader(Path(a.model_dir), threads=4)
    meta = json.loads((WORK / "crops_meta.json").read_text(encoding="utf-8"))
    hand = json.loads((WORK / "hand_lines_clean.json").read_text(encoding="utf-8"))
    blind = set(json.loads((WORK / "hand_blind.json").read_text(encoding="utf-8"))["keys"])
    by_key = {f"{r['stem']}__{r['side']}": r for r in meta}

    X, Y, B, KEYS, AUX = [], [], [], [], []
    skipped = 0
    for key, rec in sorted(hand.items()):
        r = by_key.get(key)
        if r is None or rec.get("y_surf") is None:
            skipped += 1
            continue
        path = ARCHIVE / f"{r['stem']}.jpg"
        if not path.exists():
            skipped += 1
            continue
        rgb = Frame(path.read_bytes(), 0.0, 0.0).rgb()
        if rgb is None:
            skipped += 1
            continue
        pots, _ = reader.read_pots(rgb, [{"side": r["side"], "box": r["box"], "score": 0.9}],
                                   1, with_rows=True)
        if not pots or "rowdist" not in pots[0]:
            skipped += 1
            continue
        q = pots[0]
        rd = q["rowdist"]
        n = rd["n"]
        # hand clicks are fractions of crop height, the same coordinates the row
        # head works in, so the clicked surface is simply a row index
        target = float(rec["y_surf"]) * (n - 1)
        if not (0 <= target <= n - 1):
            skipped += 1
            continue
        X.append(np.stack([rd["surf"], rd["base"], rd["top"]]).astype(np.float32))
        Y.append(target)
        B.append(key in blind)
        KEYS.append(key)
        # geometry and the two trained quality heads: the head may use them to
        # decide how wide, or how bimodal, the answer should be
        AUX.append([rd["y_base"], rd["y_top"], q["u"], q["v"], q["d"]])

    X = np.asarray(X, dtype=np.float32)
    Y = np.asarray(Y, dtype=np.float32)
    B = np.asarray(B, dtype=bool)
    AUX = np.asarray(AUX, dtype=np.float32)
    np.savez_compressed(a.out, X=X, Y=Y, blind=B, aux=AUX, keys=np.array(KEYS))
    print(f"records {len(Y)} (skipped {skipped})  train {int((~B).sum())}  blind {int(B.sum())}")
    print(f"rows {X.shape[-1]}  target row: min {Y.min():.1f} max {Y.max():.1f} mean {Y.mean():.1f}")

    # sanity: on confident frames the frozen soft-argmax should already sit near
    # the click, otherwise the coordinate convention is wrong
    rows = X.shape[-1]
    grid = np.arange(rows, dtype=np.float32)
    p = np.exp(X[:, 0] - X[:, 0].max(axis=-1, keepdims=True))
    p /= p.sum(axis=-1, keepdims=True)
    soft = (p * grid).sum(axis=-1)
    err = np.abs(soft - Y)
    print(f"frozen soft-argmax vs click, rows: median {np.median(err):.1f}  p90 {np.percentile(err, 90):.1f}")
    print("-> " + str(a.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
