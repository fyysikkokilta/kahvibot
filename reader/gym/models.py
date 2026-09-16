"""Model gym: score reader checkpoints the way the product needs them scored.

For each candidate checkpoint:
  1. export to ONNX (+ its calibration) into _work/onnx_<tag>/
  2. blind hand-click accuracy (coffee10.eval_hand --only-blind, 99 frozen records)
  3. field set (kahviraspi 2026-08-29..09-09 frames, human clicks from the survey):
     error vs human surface, entropy distribution, coverage at gates,
     and — the product question — error of the readings each gate lets through
  4. coverage on an archive day (Jan-Jun 2026) at the same gates
  5. Pi-projected cost (all candidates share the trunk; measured once)
Writes BENCH_MODELS.md + bench_models.json.

    cd coffee_mesh_pred
    python -m gym.models --candidates v8=_work/model_v8/best.pt v20last=_work/model_v20/last.pt
"""
from __future__ import annotations

import os
for _v in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import argparse
import json
import shutil
import statistics as st
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
C10 = HERE.parent
REPO = C10.parent
ROOT = REPO.parent
for p in (str(C10), str(REPO)):
    if p not in sys.path:
        sys.path.insert(0, p)
from gym.paths import ARCHIVE, COFFEE_ROOT, KAHVIBOT, RESEARCH, WORK  # noqa: E402,F401

from pipeline.reader import WarmReader        # noqa: E402
from pipeline.camera import Frame             # noqa: E402
from gym.archive import FrameArchive          # noqa: E402

GATES = (0.55, 0.58, 0.60, 0.62, 0.65, 0.70)
FULL_ML = 1250.0


def run(cmd, log: Path | None = None) -> int:
    print("  $", " ".join(cmd), flush=True)
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(RESEARCH))
    if log:
        log.write_text(r.stdout + "\n--- stderr ---\n" + r.stderr, encoding="utf-8")
    if r.returncode != 0:
        print(r.stderr[-1500:])
    return r.returncode


def export(tag: str, ckpt: str, calib: str | None) -> Path:
    out = WORK / f"onnx_{tag}"
    if not (out / "reader.onnx").exists():
        run([sys.executable, "-m", "coffee10.export_onnx", "--ckpt", ckpt, "--out-dir", str(out)],
            out / "export.log" if out.exists() else None)
    if calib and Path(calib).exists():
        shutil.copyfile(calib, out / "calibration.json")
    elif not (out / "calibration.json").exists():
        shutil.copyfile(WORK / "calibration.json", out / "calibration.json")
    return out


def find_calibration(tag: str, ckpt: str) -> str | None:
    """Per-checkpoint calibration if one was fitted; fit one otherwise."""
    cands = [WORK / f"calibration_{tag}.json"]
    m = Path(ckpt).parent.name.replace("model_", "")
    cands += [WORK / f"calibration_{m}.json", WORK / f"calibration_{m}_best.json"]
    for c in cands:
        if c.exists():
            return str(c)
    out = WORK / f"calibration_{tag}.json"
    rc = run([sys.executable, "-m", "coffee10.evaluate", "--ckpt", ckpt, "--eras", "hd,hd2026",
              "--threads", "6", "--calib-out", str(out), "--out", str(WORK / f"eval_report_{tag}.json")],
             WORK / f"eval_{tag}.log")
    return str(out) if rc == 0 and out.exists() else None


def blind_hand(tag: str, ckpt: str, calib: str | None) -> dict:
    out = WORK / f"eval_hand_gym_{tag}.json"
    if not out.exists():          # cached: the blind set and the checkpoint are both frozen
        cmd = [sys.executable, "-m", "coffee10.eval_hand", "--ckpt", ckpt, "--only-blind", "--tta", "8",
               "--threads", "6", "--out", str(out)]
        if calib:
            cmd += ["--calib", calib]
        rc = run(cmd, WORK / f"eval_hand_gym_{tag}.log")
        if rc != 0 or not out.exists():
            return {"error": "eval_hand failed"}
    r = json.loads(out.read_text(encoding="utf-8"))
    fe, ne = r.get("fill_error", {}), r.get("fill_error_nonempty", {}) or {}
    return {"n": fe.get("n"), "fill_median_ml": fe.get("median_ml"), "fill_p90_ml": fe.get("p90_ml"),
            "within_25ml": fe.get("frac_within_25ml"), "nonempty_median_ml": ne.get("median_ml"),
            "nonempty_n": ne.get("n"), "surf_median_ml": r.get("per_line_error", {}).get("y_surf", {}).get("median_ml"),
            "bias_ml": r.get("bias_ml"), "pearson_h": r.get("pearson_h")}


class FieldSet:
    """Field frames + boxes (field cache meta) + human surface labels."""

    def __init__(self):
        self.meta = json.loads((WORK / "field_meta.json").read_text(encoding="utf-8"))
        self.hand = json.loads((WORK / "hand_lines_field.json").read_text(encoding="utf-8"))
        self.blind = set(json.loads((WORK / "hand_blind_field.json").read_text(encoding="utf-8"))["keys"])
        self.frames_dir = WORK / "field_frames"
        self._rgb = {}

    def rgb(self, stem):
        if stem not in self._rgb:
            if len(self._rgb) > 8:
                self._rgb.pop(next(iter(self._rgb)))
            self._rgb[stem] = Frame((self.frames_dir / f"{stem}.jpg").read_bytes(), 0.0, 0.0).rgb()
        return self._rgb[stem]

    def pots(self, reader: WarmReader, tta: int):
        """Read every field pot with the cache's own box. Yields (key, pot, human_h|None)."""
        by_stem = {}
        for r in self.meta:
            by_stem.setdefault(r["stem"], []).append(r)
        for stem, rows in by_stem.items():
            rgb = self.rgb(stem)
            if rgb is None:
                continue
            dets = [{"side": r["side"], "box": r["box"], "score": r.get("score", 0.9)} for r in rows]
            pots, _ = reader.read_pots(rgb, dets, tta)
            for p in pots:
                key = f"{stem}__{p['side']}"
                hl = self.hand.get(key)
                hh = None
                if hl and hl.get("y_surf") is not None:
                    hh = (hl["y_base"] - hl["y_surf"]) / (hl["y_base"] - hl["y_top"])
                yield key, p, hh


def field_eval(reader: WarmReader, fs: FieldSet, tta: int = 1) -> dict:
    rows = list(fs.pots(reader, tta))
    es = [p["e"] for _, p, _ in rows]
    res = {"pots": len(rows), "tta": tta, "entropy_median": round(st.median(es), 4),
           "coverage": {}, "labelled": {}}
    for g in GATES:
        passed = [p for _, p, _ in rows if p["e"] <= g]
        res["coverage"][str(g)] = {"frac": round(len(passed) / max(1, len(rows)), 3),
                                   "nonempty_ge_125ml": sum(p["ml"] >= 125 for p in passed)}
    lab = [(k, p, hh) for k, p, hh in rows if hh is not None]
    if lab:
        err = [abs(p["h"] - hh) * FULL_ML for _, p, hh in lab]       # ml on the linear scale
        ne = [(k, p, hh) for k, p, hh in lab if hh >= 0.1]           # non-empty by the human's click
        ne_err = [abs(p["h"] - hh) * FULL_ML for _, p, hh in ne]
        res["labelled"] = {"n": len(lab), "n_blind": sum(k in fs.blind for k, _, _ in lab),
                           "abs_err_ml_median": round(st.median(err), 1),
                           "abs_err_ml_p90": round(sorted(err)[int(0.9 * (len(err) - 1))], 1),
                           "human_h_median": round(st.median(hh for _, _, hh in lab), 3),
                           "nonempty_n": len(ne),
                           "nonempty_err_median": round(st.median(ne_err), 1) if ne_err else None,
                           "by_gate": {}}
        for g in GATES:
            inn = [abs(p["h"] - hh) * FULL_ML for _, p, hh in lab if p["e"] <= g]
            out = [abs(p["h"] - hh) * FULL_ML for _, p, hh in lab if p["e"] > g]
            inn_ne = [abs(p["h"] - hh) * FULL_ML for _, p, hh in ne if p["e"] <= g]
            out_ne = [abs(p["h"] - hh) * FULL_ML for _, p, hh in ne if p["e"] > g]
            res["labelled"]["by_gate"][str(g)] = {
                "kept": len(inn), "kept_err_median": round(st.median(inn), 1) if inn else None,
                "rejected": len(out), "rejected_err_median": round(st.median(out), 1) if out else None,
                "kept_nonempty": len(inn_ne), "kept_nonempty_err": round(st.median(inn_ne), 1) if inn_ne else None,
                "rejected_nonempty": len(out_ne), "rejected_nonempty_err": round(st.median(out_ne), 1) if out_ne else None}
    return res


def archive_coverage(reader: WarmReader, frames, tta: int = 1) -> dict:
    pots = []
    for f in frames:
        rgb = Frame(f.read(), f.epoch, 0.0).rgb()
        dets, _ = reader.detect_timed(rgb)
        p, _ = reader.read_pots(rgb, dets, tta)
        pots.extend(p)
    out = {"pots": len(pots), "entropy_median": round(st.median(p["e"] for p in pots), 4) if pots else None}
    for g in GATES:
        passed = [p for p in pots if p["e"] <= g]
        out[str(g)] = {"frac": round(len(passed) / max(1, len(pots)), 3),
                       "nonempty_ge_125ml": sum(p["ml"] >= 125 for p in passed)}
    return out


def microbench(reader: WarmReader, frames) -> dict:
    d, r1, r8 = [], [], []
    for f in frames:
        rgb = Frame(f.read(), f.epoch, 0.0).rgb()
        dets, dt = reader.detect_timed(rgb)
        d.append(dt)
        _, dt1 = reader.read_pots(rgb, dets, 1)
        r1.append(dt1)
        _, dt8 = reader.read_pots(rgb, dets, 8)
        r8.append(dt8)
    return {"detect_s": st.median(d), "read_tta1_s": st.median(r1), "read_tta8_s": st.median(r8)}


def write_report(path: Path, results: list[dict], micro: dict, scale: float, meta: dict):
    L = ["# Model gym — %s\n" % meta["when"],
         "Candidates scored on: the frozen blind hand-click set (99 records, Jan–Jun 2026 camera), "
         "the field set (%d pots on %d kahviraspi frames from 2026-08-29..09-09, %d with human surface "
         "clicks from the Telegram survey, %d of those blind), and an archive day for coverage. "
         "Errors are |Δh|×1250 ml on the linear scale (the survey clicks give surface rows, not volumes).\n"
         % (meta["field_pots"], meta["field_frames"], meta["field_labelled"], meta["field_blind"])]
    L.append("## 1. Accuracy\n")
    L.append("| model | blind fill median ml | blind non-empty median ml | within 25 ml | field err median ml (n) | field non-empty err ml (n) | field err p90 ml |\n|---|---|---|---|---|---|---|")
    for r in results:
        b, f = r["blind"], r["field"].get("labelled", {})
        L.append("| %s | %s | %s | %s | %s (%s) | %s (%s) | %s |" % (
            r["tag"], b.get("fill_median_ml"), b.get("nonempty_median_ml"), b.get("within_25ml"),
            f.get("abs_err_ml_median"), f.get("n"), f.get("nonempty_err_median"), f.get("nonempty_n"),
            f.get("abs_err_ml_p90")))
    L.append("\n## 2. Coverage at the entropy gate (share of pots that would be shown)\n")
    L.append("| model | set | median e | " + " | ".join("≤%.2f" % g for g in GATES) + " |\n|---|---|---|" + "---|" * len(GATES))
    for r in results:
        f = r["field"]
        L.append("| %s | field (%d pots) | %.3f | %s |" % (r["tag"], f["pots"], f["entropy_median"],
                 " | ".join("%.0f%%" % (100 * f["coverage"][str(g)]["frac"]) for g in GATES)))
        a = r["archive"]
        L.append("| %s | archive (%d pots) | %.3f | %s |" % (r["tag"], a["pots"], a["entropy_median"],
                 " | ".join("%.0f%%" % (100 * a[str(g)]["frac"]) for g in GATES)))
    L.append("\n## 3. What each gate lets through on the field set (labelled pots)\n")
    L.append("Median |error| of kept vs rejected readings, all labelled pots and the non-empty subset "
             "(human h ≥ 0.1; empties are easy and inflate every pooled number). A gate that works keeps the accurate ones.\n")
    L.append("| model | gate | kept (err ml) | rejected (err ml) | kept non-empty (err ml) | rejected non-empty (err ml) |\n|---|---|---|---|---|---|")
    for r in results:
        bg = r["field"].get("labelled", {}).get("by_gate", {})
        for g in GATES:
            x = bg.get(str(g))
            if x:
                L.append("| %s | %.2f | %d (%s) | %d (%s) | %d (%s) | %d (%s) |" % (
                    r["tag"], g, x["kept"], x["kept_err_median"], x["rejected"], x["rejected_err_median"],
                    x.get("kept_nonempty", 0), x.get("kept_nonempty_err"), x.get("rejected_nonempty", 0), x.get("rejected_nonempty_err")))
    L.append("\n## 4. Cost (identical trunk for all candidates)\n")
    L.append("| stage | local s | Pi-projected s |\n|---|---|---|")
    for k, v in micro.items():
        L.append("| %s | %.3f | %.2f |" % (k, v, v * scale))
    L.append("\nTraining args differences and notes:\n")
    for r in results:
        L.append("* **%s** — %s" % (r["tag"], r.get("note", "")))
    path.write_text("\n".join(L) + "\n", encoding="utf-8")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--candidates", nargs="+", required=True, help="tag=path/to/ckpt ...")
    ap.add_argument("--notes", nargs="*", default=[], help="tag=free text")
    ap.add_argument("--archive-frames", type=int, default=150)
    ap.add_argument("--skip-blind", action="store_true")
    ap.add_argument("--pi-scale", type=float, default=12.9, help="from gym/bench.py")
    ap.add_argument("--out", default=str(HERE / "BENCH_MODELS.md"))
    ap.add_argument("--json", default=str(HERE / "bench_models.json"))
    a = ap.parse_args(argv)
    notes = dict(n.split("=", 1) for n in a.notes)

    archive = FrameArchive([ARCHIVE])
    day = archive.densest_days(1)[0][0]
    arch_frames = archive.on_day(day)[:: max(1, len(archive.on_day(day)) // a.archive_frames)][: a.archive_frames]
    fs = FieldSet()
    results, micro = [], None
    for spec in a.candidates:
        tag, ckpt = spec.split("=", 1)
        print(f"=== {tag}: {ckpt}", flush=True)
        t0 = time.perf_counter()
        calib = find_calibration(tag, ckpt)
        onnx_dir = export(tag, ckpt, calib)
        reader = WarmReader(onnx_dir, threads=2)
        blind = {} if a.skip_blind else blind_hand(tag, ckpt, calib)
        field = field_eval(reader, fs, tta=1)
        arch = archive_coverage(reader, arch_frames, tta=1)
        if micro is None:
            micro = microbench(reader, arch_frames[:10])
        results.append({"tag": tag, "ckpt": ckpt, "calibration": calib, "onnx": str(onnx_dir),
                        "blind": blind, "field": field, "archive": arch, "note": notes.get(tag, ""),
                        "seconds": round(time.perf_counter() - t0)})
        print(f"  blind={blind} field_err={field.get('labelled', {}).get('abs_err_ml_median')} "
              f"field_cov0.55={field['coverage']['0.55']['frac']} ({round(time.perf_counter() - t0)} s)", flush=True)
    meta = {"when": datetime.now().isoformat(timespec="minutes"), "field_pots": field["pots"],
            "field_frames": len({r['stem'] for r in fs.meta}), "field_labelled": field.get("labelled", {}).get("n", 0),
            "field_blind": field.get("labelled", {}).get("n_blind", 0), "archive_day": str(day)}
    Path(a.json).write_text(json.dumps({"results": results, "micro": micro, "meta": meta}, indent=1, default=str), encoding="utf-8")
    write_report(Path(a.out), results, micro, a.pi_scale, meta)
    print("report ->", a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
