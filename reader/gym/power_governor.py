"""Battery governor for long CPU jobs on this laptop.

The wall adapter cannot supply what 20 threads draw, so the battery discharges
even when plugged in. This watches the battery and SUSPENDS the heavy coffee10
processes (training, evaluation, gym) when it falls below LOW, RESUMES them once
it is back above HIGH, and logs the battery trend every few minutes.

    python -m gym.power_governor            # runs until _work/power_governor.stop exists
"""
from __future__ import annotations

import sys
import time
from datetime import datetime
from pathlib import Path

import psutil

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gym.paths import ARCHIVE, COFFEE_ROOT, KAHVIBOT, RESEARCH, WORK  # noqa: E402,F401

LOG = WORK / "power.log"
STOP = WORK / "power_governor.stop"
LOW, HIGH = 40.0, 75.0     # the laptop shut down once overnight under full load; keep a wide margin
MARKERS = ("coffee10.train", "coffee10.evaluate", "coffee10.eval_hand", "coffee10.gym.models",
           "coffee10.gym.bench", "coffee10.export_onnx")


def heavy_procs():
    out = []
    for p in psutil.process_iter(["pid", "cmdline"]):
        cl = p.info["cmdline"] or []
        if any(m in cl for m in MARKERS) or any(any(m in a for m in MARKERS) for a in cl):
            out.append(p)
    return out


def log(msg: str) -> None:
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def main() -> int:
    paused: list[psutil.Process] = []
    last_report = 0.0
    log(f"governor up: suspend heavy jobs below {LOW:.0f}%, resume above {HIGH:.0f}%")
    while not STOP.exists():
        b = psutil.sensors_battery()
        now = time.time()
        if b is not None:
            if now - last_report >= 300:
                log(f"battery {b.percent:.0f}% plugged={b.power_plugged} cpu={psutil.cpu_percent(interval=1):.0f}% "
                    f"heavy={len(heavy_procs())} paused={len(paused)}")
                last_report = now
            if not paused and b.percent < LOW:
                for p in heavy_procs():
                    try:
                        p.suspend()
                        paused.append(p)
                    except psutil.Error:
                        pass
                log(f"battery {b.percent:.0f}% < {LOW:.0f}%: suspended {len(paused)} processes")
            elif paused and (b.percent >= HIGH or (b.power_plugged and b.percent >= LOW + 15)):
                n = 0
                for p in paused:
                    try:
                        p.resume()
                        n += 1
                    except psutil.Error:
                        pass
                log(f"battery {b.percent:.0f}%: resumed {n} processes")
                paused = []
            elif paused:
                # new heavy processes started while paused (a chain moved on): pause them too
                for p in heavy_procs():
                    if p not in paused:
                        try:
                            p.suspend()
                            paused.append(p)
                        except psutil.Error:
                            pass
        time.sleep(30)
    for p in paused:
        try:
            p.resume()
        except psutil.Error:
            pass
    log("governor stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
