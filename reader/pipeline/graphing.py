"""Today's series in memory and a graph cache that actually hits.

The service keeps every record of the local day. /graph renders through the
kahvibot `graphs` module (Pillow, hand-drawn) but the cache key is
(local_date, seq of the last *usable* reading, gate) with a TTL, instead of the
log file's mtime, which the sampler bumps every flush.
"""
from __future__ import annotations

import importlib.util
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path


def load_kahvibot_graphs(path: str | Path):
    """Import kahvibot/graphs.py from an arbitrary checkout path."""
    path = Path(path)
    spec = importlib.util.spec_from_file_location("kahvibot_graphs", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["kahvibot_graphs"] = mod
    spec.loader.exec_module(mod)
    return mod


from . import graph_recent  # noqa: E402

log = logging.getLogger("kahvi.graph")


class DayBuffer:
    """Records for the current local day, in the store schema, plus the gate
    view the graph needs (side/ok/volume_ml)."""

    def __init__(self):
        self.day = None
        self.records: list[dict] = []

    def seed_from_log(self, path, wall: float, max_bytes: int = 8 * 1024 * 1024) -> int:
        """Load today's records from the readings log.

        The service writes every reading to disk and then, on restart, behaved as
        if the day had never happened: an empty buffer means /graph answers "not
        enough readings yet" for an hour after any restart or power cut. Reading
        back the tail of the file costs milliseconds and removes that hole.

        Only the current local day is kept, matching add()'s contract. Malformed
        lines are skipped rather than fatal: a truncated last line is the normal
        result of a power loss, which is exactly when this path matters.
        """
        import json
        import os

        day = datetime.fromtimestamp(wall).date()
        self.day, self.records = day, []
        try:
            size = os.path.getsize(path)
            with open(path, "rb") as fh:
                if size > max_bytes:
                    fh.seek(size - max_bytes)
                    fh.readline()          # drop the partial line
                blob = fh.read().decode("utf-8", "replace")
        except OSError:
            return 0
        for line in blob.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            t = rec.get("t")
            if not t or "pots" not in rec:
                continue
            try:
                when = datetime.fromisoformat(t)
            except ValueError:
                continue
            if when.astimezone().date() == day:
                self.records.append(rec)
        return len(self.records)

    def add(self, rec: dict, wall: float) -> None:
        day = datetime.fromtimestamp(wall).date()
        if day != self.day:
            self.day = day
            self.records = []
        self.records.append(rec)

    def graph_records(self, gate):
        """Widen to the shape graphs.DaySeries expects: '_t' aware datetime and
        pots with side/ok/volume_ml; ok per the given gate (uncertain counts
        as usable for the curve, drawn wider by a future graphs change)."""
        out = []
        for r in self.records:
            if "pots" not in r:
                continue
            pots = []
            for p in r["pots"]:
                tier = gate.tier_pot(p)
                pot = {"side": p["s"], "ok": tier != "abstain",
                       "volume_ml": p["ml"] if tier != "abstain" else None,
                       "tier": tier}
                # the filter's posterior, when the service is running it: the
                # graph draws the band and the temperature from these
                for src_key, dst in (("t_c", "temp_c"), ("fm", "f_ml"),
                                     ("flo", "f_lo"), ("fhi", "f_hi")):
                    if p.get(src_key) is not None:
                        pot[dst] = p[src_key]
                pots.append(pot)
            when = datetime.fromisoformat(r["t"])
            out.append({"_t": when, "_wall": when.timestamp(),
                        "pots": pots, "src": r.get("src")})
        return out


class GraphCache:
    def __init__(self, graphs_mod, gate, ttl_s: float = 600.0, font_dir=None,
                 power=None, window_s: float = 3 * 3600.0):
        self.g = graphs_mod
        self.power = power           # PowerBus, for the strip under each pot
        self.window_s = float(window_s)
        self.gate = gate
        self.ttl_s = ttl_s
        self.font_dir = font_dir
        self.key = None
        self.png = None
        self.caption = None
        self.rendered_mono = -1e18
        self.renders = 0
        self.hits = 0
        self.render_seconds = 0.0

    def get(self, daybuf: DayBuffer, last_usable_seq: int, clock):
        """(png_bytes|None, caption). Renders only when the last usable reading
        changed and the TTL has passed since the last render."""
        import time
        now_wall = clock.wall()
        now_utc = datetime.fromtimestamp(now_wall, timezone.utc)
        day = datetime.fromtimestamp(now_wall).date().isoformat()
        key = (day, last_usable_seq, self.gate)
        if key == self.key or (self.key is not None and self.key[0] == day
                               and clock.mono() - self.rendered_mono < self.ttl_s):
            self.hits += 1
            return self.png, self.caption
        records = daybuf.graph_records(self.gate)
        t0 = time.perf_counter()
        if not records:
            png, caption = None, self.g.TEXT_EMPTY
        else:
            png = None
            try:
                hist = {}
                if self.power is not None:
                    for side in ("left", "right"):
                        hist[side] = self.power.history(side, now_wall - self.window_s)
                png = graph_recent.render(records, hist, now_wall,
                                          window_s=self.window_s, font_dir=self.font_dir)
            except Exception:  # noqa: BLE001 - fall back rather than lose /graph
                log.warning("recent graph failed; falling back to the day graph",
                            exc_info=True)
            if png is not None:
                caption = None
            else:
                series = self.g.DaySeries(records, now_utc)
                if not series.enough_for_graph():
                    png, caption = None, self.g._text_not_enough(series.n_readable)
                else:
                    png = self.g.render_day_graph(series, font_dir=self.font_dir)
                    caption = self.g.build_caption(series)
        self.render_seconds += time.perf_counter() - t0
        self.renders += 1
        self.key, self.png, self.caption = key, png, caption
        self.rendered_mono = clock.mono()
        return png, caption
