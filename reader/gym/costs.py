"""Pi 3B cost model, anchored to what the Pi's own logs measured.

Measured on kahviraspi 2026-08-29..09-09 (kahviraspi_logs_2026-09-09/):
  * bot reader subprocess, read only (captured_at - read_at): median 8 s, max 10 s,
    TTA=8, fresh detect, no CPU quota
  * legacy sampler lit tick under CPUQuota=25%: 33 s cadence = 10 s interval + 23 s
    tick wall; TTA=8 probe ticks 106 s cadence; dark ticks exactly 60 s
  * fswebcam -S 20 at 1280x720: ~2 s (README; consistent with 13 s user latency
    = 2 s capture + ~8 s read + ~3 s cold start/upload)
Everything else here is an assumption and is labelled as such.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PiCosts:
    capture_s: float = 2.0                # fswebcam wall time (measured-ish)
    capture_cpu_s: float = 1.0            # ASSUMPTION: CPU share of the capture
    cold_start_s: float = 3.0             # ASSUMPTION: python + onnxruntime import + model load
    pi_tta8_read_s: float = 8.0           # MEASURED: detect + TTA=8 read on the Pi
    legacy_tick_wall_s: float = 23.0      # MEASURED: 33 s cadence - 10 s interval
    legacy_probe_wall_s: float = 96.0     # MEASURED: 106 s - 10 s
    legacy_dark_tick_wall_s: float = 8.0  # ASSUMPTION: capture under quota, no read
    legacy_quota: float = 0.25            # kahvisampler.service CPUQuota
    bot_upload_s: float = 3.0             # ASSUMPTION: Telegram photo upload on guild WiFi; occupies the
                                          # bot's single dispatcher thread in both designs
    scale: float = 32.0                   # Pi seconds per local second, set by calibrate()

    def calibrate(self, local_tta8_read_s: float) -> "PiCosts":
        """Pin the desktop->Pi factor on the one inference the Pi logs measured."""
        self.scale = self.pi_tta8_read_s / max(local_tta8_read_s, 1e-6)
        return self

    def legacy_tick_cpu_s(self) -> float:
        return self.legacy_tick_wall_s * self.legacy_quota

    def legacy_probe_cpu_s(self) -> float:
        return self.legacy_probe_wall_s * self.legacy_quota

    def legacy_dark_tick_cpu_s(self) -> float:
        return self.legacy_dark_tick_wall_s * self.legacy_quota
