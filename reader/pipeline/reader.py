"""Warm reader: the ONNX sessions are loaded once and every call is a plain
function. Numerics are read_frame.py's exactly (same crop chain, same TTA rng
stream); only the output changes: millilitres are always reported and the
ok decision is left to `gate.Gate`."""
from __future__ import annotations

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

    def read_pots(self, rgb: np.ndarray, dets, tta_views: int = 1, ident: str | None = None):
        """Read the given detections. Returns (pots, local_seconds)."""
        t0 = time.perf_counter()
        pots = self._read_pots(rgb, dets, tta_views)
        dt = time.perf_counter() - t0
        self.n_read += 1
        self.n_views += len(dets) * (1 + (tta_views if tta_views > 1 else 0))
        self.local_seconds += dt
        return pots, dt

    def _read_pots(self, rgb, dets, tta_views):
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
        return pots


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
