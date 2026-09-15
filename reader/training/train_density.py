"""Fit a small calibrated density head on top of the frozen v8 reader.

The problem it solves
---------------------
v8's row head is trained with its loss on the *soft-argmax* of its logits, so the
expectation is supervised and the shape around it is not. Measured on blind hand
clicks, reading that softmax as a likelihood is clearly worse than the point
estimate it yields, while its expectation reproduces the point estimate exactly.
A filter needs a density, not a point, so the shape has to be supervised - which
is cheap, because the backbone stays frozen and only a recalibration head is fit.

Design
------
Tiny on purpose: 158 training records. The head reads the frozen network's three
row log-probability curves (surface, base, top) and its quality logits, and emits
corrected surface-row logits as

    out = surf / temperature(aux) + correction(rows)

with `correction` initialised at zero, so training starts exactly at the frozen
behaviour and can only be pushed away from it by evidence. Roughly 500
parameters. The target is a Gaussian bump at the clicked row whose width is the
measured click noise, so the head is asked for "where would a human put the
surface", which is the only ground truth available.

    python -m coffee10.train_density
    python -m coffee10.train_density --export _work/onnx_v8_logits/density.onnx
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

REPO = Path(__file__).resolve().parents[1]
WORK = REPO / "_work"
FULL_ML = 1250.0


class DensityHead(nn.Module):
    """Recalibrates frozen row logits into a supervised density."""

    def __init__(self, rows: int = 256, ch: int = 8, k: int = 5, n_aux: int = 5):
        super().__init__()
        self.rows = rows
        self.conv = nn.Sequential(
            nn.Conv1d(3, ch, k, padding=k // 2), nn.ReLU(inplace=True),
            nn.Conv1d(ch, ch, k, padding=2 * (k // 2), dilation=2), nn.ReLU(inplace=True),
            nn.Conv1d(ch, 1, 1),
        )
        # start as the identity: zero correction, unit temperature
        nn.init.zeros_(self.conv[-1].weight)
        nn.init.zeros_(self.conv[-1].bias)
        self.aux = nn.Sequential(nn.Linear(n_aux, 8), nn.Tanh(), nn.Linear(8, 1))
        nn.init.zeros_(self.aux[-1].weight)
        nn.init.zeros_(self.aux[-1].bias)

    def forward(self, x: torch.Tensor, aux: torch.Tensor) -> torch.Tensor:
        # x: (B, 3, rows) log-probs; aux: (B, n_aux)
        log_t = self.aux(aux).squeeze(-1).clamp(-2.0, 2.0)      # log temperature
        corr = self.conv(x).squeeze(1)                           # (B, rows)
        out = x[:, 0] / torch.exp(log_t).unsqueeze(-1) + corr
        return F.log_softmax(out, dim=-1)


def soft_target(y: torch.Tensor, rows: int, sd_rows: float) -> torch.Tensor:
    grid = torch.arange(rows, dtype=torch.float32, device=y.device).unsqueeze(0)
    d = (grid - y.unsqueeze(-1)) / sd_rows
    t = torch.exp(-0.5 * d * d)
    return t / t.sum(dim=-1, keepdim=True)


def summarise(logp: np.ndarray, aux: np.ndarray, rows: int):
    """Point estimate, spread and credible interval in row units."""
    p = np.exp(logp)
    p = p / p.sum(axis=-1, keepdims=True)
    grid = np.arange(rows)
    mean = (p * grid).sum(axis=-1)
    var = (p * (grid - mean[:, None]) ** 2).sum(axis=-1)
    cdf = np.cumsum(p, axis=-1)
    q = lambda f: np.array([np.searchsorted(c, f) for c in cdf], dtype=float)
    return mean, np.sqrt(var), q(0.05), q(0.95), q(0.25), q(0.75)


def rows_to_ml(rows_err: np.ndarray, aux: np.ndarray, n_rows: int) -> np.ndarray:
    """A row error becomes a volume error through this pot's own geometry."""
    span = np.abs(aux[:, 0] - aux[:, 1])                     # y_base - y_top
    return rows_err / (n_rows - 1) / np.maximum(span, 1e-3) * FULL_ML


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", default=str(WORK / "density_ds.npz"))
    ap.add_argument("--epochs", type=int, default=400)
    ap.add_argument("--lr", type=float, default=3e-3)
    ap.add_argument("--wd", type=float, default=1e-3)
    ap.add_argument("--sd-rows", type=float, default=3.3, help="click noise, measured")
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--export", default=str(WORK / "onnx_v8_logits" / "density.onnx"))
    ap.add_argument("--report", default=str(WORK / "density_report.json"))
    a = ap.parse_args(argv)

    d = np.load(a.data, allow_pickle=True)
    X, Y, blind, AUX = d["X"], d["Y"], d["blind"], d["aux"]
    rows = X.shape[-1]
    torch.manual_seed(a.seed)

    # normalise aux so the tiny MLP sees sane scales
    mu, sd = AUX[~blind].mean(0), AUX[~blind].std(0) + 1e-6
    AUXn = (AUX - mu) / sd

    xt = torch.tensor(X[~blind]); yt = torch.tensor(Y[~blind]); at = torch.tensor(AUXn[~blind])
    xb = torch.tensor(X[blind]); yb = torch.tensor(Y[blind]); ab = torch.tensor(AUXn[blind])
    n_tr = len(yt)

    # inner cross-validation on the TRAIN split only, to choose the epoch count;
    # the blind split is never used for any decision
    rng = np.random.default_rng(a.seed)
    fold = rng.permutation(n_tr) % a.folds
    curves = np.zeros((a.folds, a.epochs))
    for f in range(a.folds):
        tr, va = fold != f, fold == f
        m = DensityHead(rows)
        opt = torch.optim.Adam(m.parameters(), lr=a.lr, weight_decay=a.wd)
        tgt = soft_target(yt[tr], rows, a.sd_rows)
        for e in range(a.epochs):
            m.train(); opt.zero_grad()
            loss = -(tgt * m(xt[tr], at[tr])).sum(-1).mean()
            loss.backward(); opt.step()
            with torch.no_grad():
                m.eval()
                vt = soft_target(yt[va], rows, a.sd_rows)
                curves[f, e] = float(-(vt * m(xt[va], at[va])).sum(-1).mean())
    best_epoch = int(np.argmin(curves.mean(0)) + 1)
    print(f"cross-validated epochs: {best_epoch}  (val NLL {curves.mean(0).min():.4f} "
          f"vs {curves.mean(0)[0]:.4f} at init = frozen model)")

    model = DensityHead(rows)
    opt = torch.optim.Adam(model.parameters(), lr=a.lr, weight_decay=a.wd)
    tgt = soft_target(yt, rows, a.sd_rows)
    for _ in range(best_epoch):
        model.train(); opt.zero_grad()
        loss = -(tgt * model(xt, at)).sum(-1).mean()
        loss.backward(); opt.step()
    model.eval()

    with torch.no_grad():
        lp_new = model(xb, ab).numpy()
    lp_old = X[blind][:, 0] - np.log(np.exp(X[blind][:, 0]).sum(-1, keepdims=True))
    yb_np, aux_b = Y[blind], AUX[blind]

    out = {}
    for name, lp in (("frozen v8 softmax", lp_old), ("density head", lp_new)):
        mean, sd_r, lo5, hi95, lo25, hi75 = summarise(lp, aux_b, rows)
        nll = float(-(soft_target(torch.tensor(yb_np), rows, a.sd_rows).numpy()
                      * lp).sum(-1).mean())
        err_ml = rows_to_ml(np.abs(mean - yb_np), aux_b, rows)
        mode_ml = rows_to_ml(np.abs(lp.argmax(-1) - yb_np), aux_b, rows)
        cov90 = float(np.mean((yb_np >= lo5) & (yb_np <= hi95)))
        cov50 = float(np.mean((yb_np >= lo25) & (yb_np <= hi75)))
        width_ml = float(np.median(rows_to_ml(hi95 - lo5, aux_b, rows)))
        sd_ml = rows_to_ml(sd_r, aux_b, rows)
        # does the posterior's own spread order the errors?
        idx = np.argsort(sd_ml)
        k = max(1, len(idx) // 5)
        out[name] = {"nll": nll, "err_mean_ml": float(np.median(err_ml)),
                     "err_mode_ml": float(np.median(mode_ml)),
                     "cov90": cov90, "cov50": cov50, "width90_ml": width_ml,
                     "err_best20pct_by_sd": float(np.median(err_ml[idx[:k]])),
                     "err_worst20pct_by_sd": float(np.median(err_ml[idx[-k:]]))}
        print(f"\n{name}")
        for k2, v in out[name].items():
            print(f"   {k2:24s} {v:8.3f}")

    Path(a.report).write_text(json.dumps(
        {"blind_n": int(blind.sum()), "train_n": int((~blind).sum()),
         "best_epoch": best_epoch, "sd_rows": a.sd_rows, "results": out,
         "aux_mean": mu.tolist(), "aux_std": sd.tolist()}, indent=1), encoding="utf-8")

    if a.export:
        p = Path(a.export)
        p.parent.mkdir(parents=True, exist_ok=True)
        torch.onnx.export(model, (xb[:1], ab[:1]), str(p),
                          input_names=["row_logp", "aux"], output_names=["surf_logp"],
                          dynamic_axes={"row_logp": {0: "batch"}, "aux": {0: "batch"},
                                        "surf_logp": {0: "batch"}},
                          opset_version=17, do_constant_folding=True)
        (p.parent / "density_meta.json").write_text(json.dumps(
            {"rows": rows, "aux_order": ["y_base", "y_top", "usable_logit", "surface_logit",
                                         "detector_score"],
             "aux_mean": mu.tolist(), "aux_std": sd.tolist(),
             "trained_on": int((~blind).sum()), "epochs": best_epoch,
             "click_sd_rows": a.sd_rows}, indent=1), encoding="utf-8")
        print(f"\nexported -> {p}  ({sum(q.numel() for q in model.parameters())} parameters)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
