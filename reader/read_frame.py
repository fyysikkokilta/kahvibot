"""Read coffee volume from one kahvibot frame. Deployment entry point.

Self-contained on purpose: this file is copied to the Raspberry Pi next to the
ONNX artifacts and runs with only numpy + Pillow + onnxruntime — no cv2, no
torch, no coffee10 package. The bot invokes it as a short-lived subprocess
(``python3 read_frame.py photo.jpg``) and reads one JSON line per frame from
stdout; any nonzero exit or garbled output must degrade to "no reading" on the
bot side.

Every cv2 call in the training pipeline is re-implemented here in numpy with
the same numerics (BT.601 fixed-point grey, area-coverage resize, integer-grid
affine sampling, the fixed binomial blur kernels cv2 substitutes for sigma=0),
because the millilitre calibration is tied to that exact preprocessing.
``verify_read_frame.py`` in the repo measures the residual disagreement; keep
it near zero LSB before shipping a change to any function in the first half of
this file.

Model files expected beside this script (or under --model-dir):
    reader.onnx (+ .data), fastbox.onnx (+ .data), calibration.json, manifest.json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image

SIDES = ("left", "right")
MIN_BOX_PX = 40  # same absolute cutoff fastbox_train uses when writing boxes


# --------------------------------------------------------------------------
# cv2-equivalent primitives
# --------------------------------------------------------------------------

def rgb_to_grey(rgb: np.ndarray) -> np.ndarray:
    """cv2.cvtColor(BGR2GRAY) bit-exact: fixed-point BT.601, >>14 with rounding."""
    r = rgb[:, :, 0].astype(np.uint32)
    g = rgb[:, :, 1].astype(np.uint32)
    b = rgb[:, :, 2].astype(np.uint32)
    return ((r * 4899 + g * 9617 + b * 1868 + 8192) >> 14).astype(np.uint8)


def _area_weights(n_in: int, n_out: int) -> np.ndarray:
    """(n_out, n_in) fractional-coverage matrix: cv2.INTER_AREA for shrinking."""
    scale = n_in / n_out
    w = np.zeros((n_out, n_in), dtype=np.float64)
    for i in range(n_out):
        lo, hi = i * scale, (i + 1) * scale
        j0, j1 = int(np.floor(lo)), int(np.ceil(hi))
        for j in range(j0, min(j1, n_in)):
            w[i, j] = min(hi, j + 1) - max(lo, j)
    return w / scale


def area_resize(img: np.ndarray, out_w: int, out_h: int) -> np.ndarray:
    """cv2.resize(..., INTER_AREA) for downscaling, rounded like cv2 (rint)."""
    h, w = img.shape[:2]
    wh = _area_weights(h, out_h)
    ww = _area_weights(w, out_w).T
    if img.ndim == 2:
        out = wh @ img.astype(np.float64) @ ww
    else:
        out = np.stack([wh @ img[:, :, c].astype(np.float64) @ ww
                        for c in range(img.shape[2])], axis=-1)
    return np.clip(np.rint(out), 0, 255).astype(np.uint8)


def bilinear_warp(img: np.ndarray, x0: float, y0: float, win_w: float,
                  win_h: float, out_w: int, out_h: int) -> np.ndarray:
    """cv2.warpAffine for a pure scale+translate map, BORDER_REPLICATE.

    warpAffine applies the (inverted) matrix to integer pixel coordinates with
    no half-pixel shift, so the source coordinate of output x is simply
    x0 + x * win_w / out_w.
    """
    h, w = img.shape[:2]
    xs = x0 + np.arange(out_w, dtype=np.float64) * (win_w / out_w)
    ys = y0 + np.arange(out_h, dtype=np.float64) * (win_h / out_h)
    xc = np.clip(xs, 0.0, w - 1.0)
    yc = np.clip(ys, 0.0, h - 1.0)
    xi = np.clip(np.floor(xc).astype(np.int64), 0, w - 2) if w > 1 else np.zeros(out_w, np.int64)
    yi = np.clip(np.floor(yc).astype(np.int64), 0, h - 2) if h > 1 else np.zeros(out_h, np.int64)
    fx = (xc - xi)[None, :, None]
    fy = (yc - yi)[:, None, None]
    p = img.astype(np.float64)
    tl = p[yi][:, xi]
    tr = p[yi][:, xi + 1] if w > 1 else tl
    bl = p[yi + 1][:, xi] if h > 1 else tl
    br = p[yi + 1][:, xi + 1] if (w > 1 and h > 1) else tl
    out = (tl * (1 - fx) * (1 - fy) + tr * fx * (1 - fy)
           + bl * (1 - fx) * fy + br * fx * fy)
    return np.clip(np.rint(out), 0, 255).astype(np.uint8)


# cv2.getGaussianKernel substitutes these fixed kernels when sigma<=0, k<=7.
_BLUR_KERNELS = {3: np.array([0.25, 0.5, 0.25], dtype=np.float32),
                 5: np.array([0.0625, 0.25, 0.375, 0.25, 0.0625], dtype=np.float32)}


def gaussian_blur(img: np.ndarray, k: int) -> np.ndarray:
    """cv2.GaussianBlur(img, (k, k), 0) on float32, BORDER_REFLECT_101."""
    kern = _BLUR_KERNELS[k]
    pad = k // 2
    out = img.astype(np.float32)
    p = np.pad(out, ((pad, pad), (0, 0), (0, 0)), mode="reflect")
    out = sum(p[i:i + out.shape[0]] * kern[i] for i in range(k))
    p = np.pad(out, ((0, 0), (pad, pad), (0, 0)), mode="reflect")
    out = sum(p[:, i:i + img.shape[1]] * kern[i] for i in range(k))
    return out


# --------------------------------------------------------------------------
# training-pipeline crop chain (ports of coffee10.crops / coffee10.dataset)
# --------------------------------------------------------------------------

def expand_box(box, width, height, margin=0.12, top_extra=0.06):
    x1, y1, x2, y2 = box
    bw, bh = x2 - x1, y2 - y1
    x1 -= bw * margin
    x2 += bw * margin
    y1 -= bh * (margin + top_extra)
    y2 += bh * margin
    return (max(0.0, x1), max(0.0, y1), min(float(width), x2), min(float(height), y2))


def model_crop(frame: np.ndarray, box, out_size=(160, 320), margin=0.12):
    """Letterbox the padded box into out_size (w, h). Returns crop + transform.

    transform = (scale, off_x, off_y, pad_x, pad_y): frame_y = (y - pad_y)/scale + off_y
    """
    height, width = frame.shape[:2]
    x1, y1, x2, y2 = expand_box(box, width, height, margin=margin)
    sub = frame[int(round(y1)): int(round(y2)), int(round(x1)): int(round(x2))]
    out_w, out_h = out_size
    if sub.size == 0:
        return np.zeros((out_h, out_w, 3), np.uint8), (1.0, x1, y1, 0, 0)
    scale = min(out_w / sub.shape[1], out_h / sub.shape[0])
    new_w = max(1, int(round(sub.shape[1] * scale)))
    new_h = max(1, int(round(sub.shape[0] * scale)))
    resized = area_resize(sub, new_w, new_h)
    canvas = np.zeros((out_h, out_w, 3), np.uint8)
    pad_x = (out_w - new_w) // 2
    pad_y = (out_h - new_h) // 2
    canvas[pad_y: pad_y + new_h, pad_x: pad_x + new_w] = resized
    return canvas, (scale, x1, y1, pad_x, pad_y)


def photometric(img: np.ndarray, rng: np.random.Generator, strength: float = 1.0) -> np.ndarray:
    """Port of coffee10.dataset.photometric. img is RGB here where the original
    was BGR, so the per-channel colour factors are reversed before use to keep
    the drawn jitter attached to the same physical channels."""
    out = img.astype(np.float32)
    out *= 1.0 + rng.uniform(-0.35, 0.35) * strength
    mean = float(out.mean())
    out = mean + (out - mean) * (1.0 + rng.uniform(-0.35, 0.45) * strength)
    colour = rng.uniform(-0.10, 0.10, size=(1, 1, 3)).astype(np.float32)
    out *= 1.0 + colour[:, :, ::-1] * strength
    out = np.clip(out, 0, 255)
    gamma = float(np.exp(rng.uniform(-0.30, 0.30) * strength))
    out = 255.0 * np.power(out / 255.0, gamma)
    if rng.random() < 0.3 * strength:
        k = int(rng.choice(np.array([3, 5])))
        out = gaussian_blur(out, k)
    if rng.random() < 0.4 * strength:
        out = out + rng.normal(0, rng.uniform(2, 9), out.shape).astype(np.float32)
    return np.clip(out, 0, 255).astype(np.uint8)


def geometric(img: np.ndarray, rng: np.random.Generator, out_size, strength: float = 1.0):
    """Port of coffee10.dataset.geometric (draw order preserved)."""
    src_h, src_w = img.shape[:2]
    out_w, out_h = out_size
    zoom = 1.0 + rng.uniform(-0.10, 0.10) * strength
    win_h = min(float(src_h), max(8.0, src_h / zoom))
    win_w = min(float(src_w), max(8.0, src_w / zoom))
    max_dy = (src_h - win_h) / 2 + src_h * 0.04 * strength
    max_dx = (src_w - win_w) / 2 + src_w * 0.05 * strength
    cy = src_h / 2 + rng.uniform(-max_dy, max_dy)
    cx = src_w / 2 + rng.uniform(-max_dx, max_dx)
    y0 = cy - win_h / 2
    x0 = cx - win_w / 2
    return bilinear_warp(img, x0, y0, win_w, win_h, out_w, out_h)


def to_chw(img_rgb: np.ndarray) -> np.ndarray:
    """coffee10.dataset.to_tensor minus the BGR->RGB flip (input is RGB)."""
    return (img_rgb.transpose(2, 0, 1).astype(np.float32) / 255.0)


# --------------------------------------------------------------------------
# calibration + reader
# --------------------------------------------------------------------------

class Calibration:
    def __init__(self, path: Path):
        d = json.loads(path.read_text(encoding="utf-8"))
        self.h_knots = d["h_knots"]
        self.f_knots = d["f_knots"]
        self.full_ml = float(d.get("full_ml", 1250.0))

    def fraction(self, h: float) -> float:
        return float(np.clip(np.interp(h, self.h_knots, self.f_knots), 0.0, 1.0))

    def ml(self, h: float) -> float:
        return self.fraction(h) * self.full_ml


class FrameReader:
    def __init__(self, model_dir: Path, threads: int = 2,
                 tta_views: int = 8, tta_strength: float = 0.5,
                 gate_entropy: float = 0.55, conf: float = 0.5):
        import onnxruntime as ort
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = threads
        opts.inter_op_num_threads = 1
        self.reader = ort.InferenceSession(str(model_dir / "reader.onnx"),
                                           opts, providers=["CPUExecutionProvider"])
        self.fastbox = ort.InferenceSession(str(model_dir / "fastbox.onnx"),
                                            opts, providers=["CPUExecutionProvider"])
        mani = json.loads((model_dir / "manifest.json").read_text(encoding="utf-8"))
        self.out_names = mani["reader_outputs"]
        self.rows = int(mani["reader"]["rows"])
        self.crop_w = int(mani["reader"]["crop_w"])
        self.cache_h = int(mani["reader"].get("cache_h", 320))
        self.cache_w = int(mani["reader"].get("cache_w", 160))
        self.box_h = int(mani["fastbox"]["in_h"])
        self.box_w = int(mani["fastbox"]["in_w"])
        self.cal = Calibration(model_dir / "calibration.json")
        self.tta_views = tta_views
        self.tta_strength = tta_strength
        self.gate_entropy = gate_entropy
        self.conf = conf

    def detect(self, rgb: np.ndarray) -> list[dict]:
        h, w = rgb.shape[:2]
        grey = rgb_to_grey(rgb)
        small = area_resize(grey, self.box_w, self.box_h)
        inp = (small.astype(np.float32) / 255.0)[None, None]
        boxes, logits = self.fastbox.run(None, {"frame": inp})
        probs = 1.0 / (1.0 + np.exp(-logits[0]))
        dets = []
        for k, side in enumerate(SIDES):
            if probs[k] < self.conf:
                continue
            x1, y1, x2, y2 = boxes[0, k]
            box = [round(float(x1 * w), 2), round(float(y1 * h), 2),
                   round(float(x2 * w), 2), round(float(y2 * h), 2)]
            if box[2] - box[0] < MIN_BOX_PX or box[3] - box[1] < MIN_BOX_PX:
                continue
            dets.append({"side": side, "box": box, "score": round(float(probs[k]), 4)})
        return dets

    def _run_reader(self, batch: np.ndarray) -> dict[str, np.ndarray]:
        outs = self.reader.run(None, {"image": batch})
        return dict(zip(self.out_names, outs))

    def read(self, rgb: np.ndarray) -> list[dict]:
        dets = self.detect(rgb)
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

        # TTA: median h_norm over jittered views; rng stream (seed 1000+v,
        # consumed crop-by-crop inside a view) matches coffee10.infer exactly.
        tta_h = None
        if self.tta_views > 1:
            views = []
            for v in range(self.tta_views):
                rng = np.random.default_rng(1000 + v)
                for crop in cache_crops:
                    warped = geometric(crop, rng, (self.crop_w, self.rows), self.tta_strength)
                    views.append(to_chw(photometric(warped, rng, self.tta_strength)))
            h_all = self._run_reader(np.stack(views))["h_norm"]
            tta_h = np.median(h_all.reshape(self.tta_views, len(dets)), axis=0)

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


def load_rgb(path: str) -> np.ndarray | None:
    try:
        with Image.open(path) as im:
            return np.asarray(im.convert("RGB"))
    except OSError:
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("paths", nargs="+", help="frame(s) to read")
    ap.add_argument("--model-dir", default=str(Path(__file__).resolve().parent))
    ap.add_argument("--threads", type=int, default=2)
    ap.add_argument("--tta-views", type=int, default=8)
    ap.add_argument("--tta-strength", type=float, default=0.5)
    ap.add_argument("--gate-entropy", type=float, default=0.55)
    ap.add_argument("--conf", type=float, default=0.5)
    args = ap.parse_args()

    try:
        reader = FrameReader(Path(args.model_dir), args.threads,
                             args.tta_views, args.tta_strength,
                             args.gate_entropy, args.conf)
    except Exception as exc:  # noqa: BLE001 - a broken install must say so plainly
        print(json.dumps({"error": f"model load failed: {exc}"}), flush=True)
        return 2

    worst = 0
    for path in args.paths:
        rec: dict = {"file": Path(path).stem,
                     "read_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        frame = load_rgb(path)
        if frame is None:
            rec["error"] = "unreadable"
            worst = max(worst, 1)
        else:
            try:
                rec["pots"] = reader.read(frame)
            except Exception as exc:  # noqa: BLE001 - one bad frame must not kill the batch
                rec["error"] = f"read failed: {exc}"
                worst = max(worst, 1)
        print(json.dumps(rec), flush=True)
    return worst


if __name__ == "__main__":
    sys.exit(main())
