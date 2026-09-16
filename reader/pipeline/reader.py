"""Warm reader: the ONNX sessions are loaded once and every call is a plain
function. Numerics are read_frame.py's exactly (same crop chain, same TTA rng
stream); only the output changes: millilitres are always reported and the
ok decision is left to `gate.Gate`."""
from __future__ import annotations

import math
import sys
import time
from pathlib import Path

import numpy as np

_HERE = Path(__file__).resolve().parent
for cand in (_HERE.parent, _HERE):            # coffee10/ (dev) or deploy dir (Pi)
    if (cand / "read_frame.py").is_file() and str(cand) not in sys.path:
        sys.path.insert(0, str(cand))
from read_frame import (  # noqa: E402
    SIDES, FrameReader, area_resize, geometric, model_crop, photometric, to_chw,
)


class WarmReader(FrameReader):
    """FrameReader with injectable boxes and per-call TTA. Returns pot dicts:
    side, h (h_norm), e (surface entropy), d (detector score), ml, fill, box,
    rows (frame px of base/top/surface). No `ok`: see gate.py."""

    def __init__(self, model_dir: Path, threads: int = 2, tta_strength: float = 0.5,
                 conf: float = 0.5):
        super().__init__(Path(model_dir), threads=threads, tta_views=1,
                         tta_strength=tta_strength, gate_entropy=1.0, conf=conf)
        self.density = None          # optional calibrated density head
        self._density_meta = None
        dpath = Path(model_dir) / "density.onnx"
        mpath = Path(model_dir) / "density_meta.json"
        if dpath.is_file() and mpath.is_file():
            import json as _json

            import onnxruntime as _ort
            _o = _ort.SessionOptions()
            _o.intra_op_num_threads = threads
            _o.inter_op_num_threads = 1
            self.density = _ort.InferenceSession(str(dpath), _o,
                                                 providers=["CPUExecutionProvider"])
            self._density_meta = _json.loads(mpath.read_text(encoding="utf-8"))
        self.n_detect = 0
        self.n_read = 0
        self.n_views = 0          # reader forward passes counted in crops x views
        self.local_seconds = 0.0  # wall time spent inside detect/read on this machine

    def detect_timed(self, rgb: np.ndarray, ident: str | None = None):
        """Returns (dets, local_seconds). `ident` names the frame for memoising
        wrappers (the gym); the real reader ignores it."""
        t0 = time.perf_counter()
        dets = self.detect(rgb)
        dt = time.perf_counter() - t0
        self.n_detect += 1
        self.local_seconds += dt
        return dets, dt

    def read_pots(self, rgb: np.ndarray, dets, tta_views: int = 1, ident: str | None = None,
                  with_rows: bool = False):
        """Read the given detections. Returns (pots, local_seconds).

        with_rows attaches the network's own row distributions (`rowdist`) to
        each pot, for consumers that want a likelihood over the surface
        position rather than a point estimate plus a confidence gate. It needs
        a model bundle exporting `line_logits`; older bundles simply omit it.
        """
        t0 = time.perf_counter()
        pots = self._read_pots(rgb, dets, tta_views, with_rows)
        dt = time.perf_counter() - t0
        self.n_read += 1
        self.n_views += len(dets) * (1 + (tta_views if tta_views > 1 else 0))
        self.local_seconds += dt
        return pots, dt

    def _read_pots(self, rgb, dets, tta_views, with_rows=False):
        if not dets:
            return []
        cache_crops, transforms = [], []
        for det in dets:
            crop, tf = model_crop(rgb, det["box"], out_size=(self.cache_w, self.cache_h))
            cache_crops.append(crop)
            transforms.append(tf)
        base = np.stack([to_chw(area_resize(c, self.crop_w, self.rows)) for c in cache_crops])
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
        pots = []
        for i, det in enumerate(dets):
            h = float(out["h_norm"][i]) if tta_h is None else float(tta_h[i])
            e = float(out["entropy"][i, 2])
            scale, off_x, off_y, pad_x, pad_y = transforms[i]

            def fy(y_norm):
                return (float(y_norm) * self.cache_h - pad_y) / scale + off_y

            pots.append({
                "side": det["side"],
                "h": round(h, 5),
                "e": round(e, 4),
                "d": det["score"],
                # the two trained quality heads, logged so a gate can be fitted
                # offline on field data instead of guessed (gym/gate2.py)
                "u": round(float(out["usable_logit"][i]), 4),
                "v": round(float(out["surface_logit"][i]), 4),
                "ml": self.cal.ml(h),              # unrounded; store.slim() rounds
                "fill": self.cal.fraction(h),
                "box": det["box"],
                "rows": {"base": round(fy(out["y_base"][i]), 1),
                         "top": round(fy(out["y_top"][i]), 1),
                         "surf": round(fy(out["y_surf"][i]), 1)},
            })
            if with_rows and "line_logits" in out:
                rd = row_dist(out["line_logits"][i],
                              float(out["y_base"][i]), float(out["y_top"][i]))
                if self.density is not None:
                    rd = self._calibrate(rd, pots[-1])
                pots[-1]["rowdist"] = rd
        return pots


    def _calibrate(self, rd: dict, pot: dict) -> dict:
        """Replace the surface curve with the trained density head's output.

        v8's row softmax is not a calibrated density - its loss only ever saw the
        soft-argmax - so used as a likelihood it is worse than the point estimate
        it produces. The head (coffee10/train_density.py, ~500 parameters on a
        frozen backbone) supervises the shape against hand clicks; on the blind
        split it restores point accuracy, reaches nominal 90 % interval coverage,
        and its spread separates good readings from bad by 3x, which entropy
        never did. `rowdist["surf_raw"]` keeps the uncalibrated curve for
        comparison.
        """
        meta = self._density_meta
        aux = np.array([[rd["y_base"], rd["y_top"], pot["u"], pot["v"], pot["d"]]],
                       dtype=np.float32)
        aux = (aux - np.asarray(meta["aux_mean"], dtype=np.float32)) /               np.asarray(meta["aux_std"], dtype=np.float32)
        x = np.stack([rd["surf"], rd["base"], rd["top"]])[None].astype(np.float32)
        lp = self.density.run(None, {"row_logp": x, "aux": aux})[0][0]
        return {**rd, "surf": lp.astype(np.float64), "surf_raw": rd["surf"],
                "calibrated": True}


def _log_softmax(x: np.ndarray) -> np.ndarray:
    m = x.max(axis=-1, keepdims=True)
    z = x - m
    return z - np.log(np.exp(z).sum(axis=-1, keepdims=True))


def row_dist(line_logits: np.ndarray, y_base: float, y_top: float) -> dict:
    """The network's three row distributions for one pot, as log-probabilities.

    `line_logits` is (3, rows) in the model's crop coordinates, ordered
    base, top, surface; the soft-argmax of each is what the point estimate uses.
    Keeping the whole distribution is what lets a filter see that a reading is
    bimodal rather than merely "uncertain" - the two surfaces it is torn between
    are two peaks, and an entropy scalar cannot tell them apart from one broad
    blur.
    """
    lp = _log_softmax(np.asarray(line_logits, dtype=np.float64))
    return {"n": int(lp.shape[-1]), "base": lp[0], "top": lp[1], "surf": lp[2],
            "y_base": float(y_base), "y_top": float(y_top)}


def surf_loglik(rd: dict, h) -> np.ndarray:
    """log p(image | h_norm = h) from the surface row distribution.

    h is mapped back to the row the surface would occupy under this pot's own
    base/top geometry, and the network's log-probability is read off there with
    linear interpolation. Values outside the crop get the floor, so a particle
    that has drifted off the vessel is penalised rather than silently clamped.
    """
    h = np.atleast_1d(np.asarray(h, dtype=np.float64))
    span = rd["y_base"] - rd["y_top"]
    y = rd["y_base"] - h * span                      # crop-normalised row position
    r = y * (rd["n"] - 1)
    lo = np.floor(r).astype(int)
    frac = r - lo
    lp = rd["surf"]
    floor = lp.min() - 2.0
    out = np.full(h.shape, floor)
    ok = (lo >= 0) & (lo < rd["n"] - 1)
    if ok.any():
        out[ok] = (1.0 - frac[ok]) * lp[lo[ok]] + frac[ok] * lp[lo[ok] + 1]
    edge = (lo == rd["n"] - 1)
    if edge.any():
        out[edge] = lp[-1]
    return out


def surf_modes(rd: dict, min_mass: float = 0.08, smooth: int = 5, max_modes: int = 4) -> list:
    """Decompose the surface row distribution into modes, each summarised by a
    LOCAL soft-argmax.

    This exists because the raw softmax is not a calibrated density. The network
    is trained with its loss on the soft-argmax of these logits, so the
    *expectation* is the quantity that was fitted to labelled surfaces; the shape
    around it was never supervised. Measured on blind hand clicks, reading the
    softmax directly as a likelihood is markedly worse than the point estimate,
    while the expectation reproduces it exactly - because the expectation is what
    the model was asked to get right.

    So each mode is summarised the way the model was trained: a soft-argmax, but
    restricted to that mode's basin. A unimodal frame therefore reproduces the
    deployed point estimate to the digit, and a bimodal frame yields the two
    candidate surfaces separately instead of an average of them that corresponds
    to no surface at all.

    Returns a list of dicts with `h` (normalised fill), `weight` (mode mass) and
    `h_sd` (spread within the basin), heaviest mode first.
    """
    p = np.exp(rd["surf"])
    p = p / p.sum()
    if smooth > 1:
        k = np.ones(smooth) / smooth
        ps = np.convolve(p, k, mode="same")
    else:
        ps = p
    n = len(p)
    peaks = [i for i in range(1, n - 1)
             if ps[i] >= ps[i - 1] and ps[i] > ps[i + 1] and ps[i] > min_mass * ps.max()]
    if not peaks:
        peaks = [int(np.argmax(ps))]
    # basin boundaries: the lowest point between neighbouring peaks
    bounds = [0]
    for a, b in zip(peaks, peaks[1:]):
        bounds.append(a + int(np.argmin(ps[a:b + 1])))
    bounds.append(n)

    span = rd["y_base"] - rd["y_top"]
    rows = np.arange(n, dtype=float)
    modes = []
    for lo, hi in zip(bounds, bounds[1:]):
        seg = p[lo:hi]
        m = seg.sum()
        if m <= 0:
            continue
        r = rows[lo:hi]
        centre = float((seg * r).sum() / m)                      # local soft-argmax
        var = float((seg * (r - centre) ** 2).sum() / m)
        y = centre / (n - 1)
        h = (rd["y_base"] - y) / span if span else 0.0
        h_sd = math.sqrt(max(var, 0.0)) / (n - 1) / abs(span) if span else 0.0
        modes.append({"h": float(h), "weight": float(m), "h_sd": float(h_sd)})
    modes.sort(key=lambda d: -d["weight"])
    return modes[:max_modes]


def legacy_pots(pots, gate_entropy: float = 0.55):
    """Render WarmReader pots in read_frame.py's exact output schema (for
    equivalence tests and for consumers that still expect it)."""
    out = []
    for p in pots:
        clean = p["e"] <= gate_entropy
        out.append({
            "side": p["side"], "ok": bool(clean),
            "volume_ml": round(p["ml"], 1) if clean else None,
            "fill_fraction": round(p["fill"], 4) if clean else None,
            "cups": round(p["ml"] / 125.0, 2) if clean else None,
            "h_norm": p["h"], "surface_entropy": p["e"], "detector_score": p["d"],
            "box": p["box"], "rows_frame_px": p["rows"],
            "reason": None if clean else
                      "diffuse surface estimate (occluded or no visible surface)",
        })
    return out
