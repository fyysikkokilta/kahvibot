"""Run the streamlined ReaderService against the archive on a virtual clock."""
from __future__ import annotations

import statistics as st
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from pipeline.camera import ArchiveCamera, ArchiveSource
from pipeline.clock import VirtualClock
from pipeline.gate import Gate
from pipeline.service import ReaderService, ServiceConfig
from pipeline.store import ReadingsStore


@dataclass
class StreamResult:
    service: ReaderService
    photo_latency: list = field(default_factory=list)
    reading_latency: list = field(default_factory=list)
    graph_calls: int = 0
    graph_renders_legacy_model: int = 0
    cpu_s: float = 0.0
    records: list = field(default_factory=list)
    workdir: Path | None = None
    bot_pots: dict = field(default_factory=dict)   # ident -> pots served to the bot (TTA=1)

    def summary(self):
        s = self.service.stats
        pl = sorted(self.photo_latency)
        rl = sorted(self.reading_latency)
        q = lambda a, p: a[min(len(a) - 1, int(p * len(a)))] if a else None
        gaps = sorted(s.tick_gaps)
        gc = self.service.graphcache
        return {
            "requests": s.requests,
            "photo_latency_p50": q(pl, 0.5), "photo_latency_p90": q(pl, 0.9),
            "photo_latency_max": pl[-1] if pl else None,
            "reading_latency_p50": q(rl, 0.5), "reading_latency_p90": q(rl, 0.9),
            "requests_reused": s.requests_reused, "requests_captured": s.requests_captured,
            "captures": s.captures,
            "sampler_lit_ticks": s.ticks - s.ticks_dark - s.ticks_skipped_busy - s.ticks_failed,
            "sampler_gap_median": st.median(gaps) if gaps else None,
            "sampler_gap_p90": q(gaps, 0.9),
            "blind_hours": None,
            "cpu_total_s": round(self.cpu_s),
            "records": len(self.records),
            "graph_calls": self.graph_calls,
            "graph_renders": gc.renders if gc else None,
            "graph_hits": gc.hits if gc else None,
            "graph_renders_legacy_key": self.graph_renders_legacy_model,
            "graph_render_local_s": round(gc.render_seconds, 3) if gc else None,
        }


def run_streamlined(archive, reader, requests: list[float], t0: float, t1: float, costs,
                    gate: Gate, cfg: ServiceConfig, graphs_mod=None,
                    graph_calls: list[float] | None = None, workdir: str | None = None,
                    source: ArchiveSource | None = None) -> StreamResult:
    clock = VirtualClock(t0, scale=costs.scale)
    cam = ArchiveCamera(archive, clock, capture_cost_s=costs.capture_s, source=source)
    workdir = Path(workdir or tempfile.mkdtemp(prefix="kahvigym-"))
    store = ReadingsStore(str(workdir / "readings-%Y-%m.jsonl"), clock, flush_sec=cfg.flush_sec,
                          latest_path=str(workdir / "latest.json"))
    svc = ReaderService(cam, reader, store, clock, gate, cfg, graphs_mod=graphs_mod)
    res = StreamResult(svc, workdir=workdir)
    events = sorted([(t, "photo") for t in requests] + [(t, "graph") for t in (graph_calls or [])])
    last_legacy_key = None
    bot_free = t0                            # kahvibot's dispatcher handles one update at a time
    for t, kind in events:
        # the bot picks the request up when its previous handler (incl. upload) is done
        t_handle = max(t, bot_free)
        # ticks due before that instant run first; the service is single-threaded
        # so a request arriving mid-tick waits for the tick to finish
        svc.run_due(until_mono=t_handle - t0)
        clock.set_wall(t_handle)
        wait = clock.wall() - t              # dispatcher queue + tick in progress
        if kind == "photo":
            r = svc.frame()
            photo = wait + svc.stats.request_photo_latency[-1]
            res.photo_latency.append(photo + costs.bot_upload_s)          # photo delivered
            res.reading_latency.append(wait + svc.stats.request_reading_latency[-1])
            bot_free = t + photo + costs.bot_upload_s
            if r is not None:
                res.bot_pots.setdefault(r.frame.ident, [dict(p) for p in r.pots])
        else:
            res.graph_calls += 1
            svc.graph()
            key = (store.appends, store.records)   # legacy key ~ (mtime, n_records)
            if key != last_legacy_key:
                res.graph_renders_legacy_model += 1
                last_legacy_key = key
    svc.run_due(until_mono=t1 - t0)
    store.flush(force=True)
    res.cpu_s = cam.captures * costs.capture_cpu_s + svc.stats.compute_charged
    res.records = list(svc.daybuf.records)
    return res
