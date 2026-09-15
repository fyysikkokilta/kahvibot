"""Single-writer readings store.

One process appends, one schema, monthly rotation via a strftime pattern, a
batched append per flush interval (SAMPLER.md §6), and an atomically replaced
`latest.json` sidecar so a consumer can learn "anything new?" without parsing
the log.

Record schema (every lit frame, whoever asked for it):
  {"t": iso-utc, "seq": n, "src": "sampler"|"bot", "luma": f,
   "pots": [{"s": side, "h": f, "e": f, "d": f, "ml": f}], "tta": n?}
Dark ticks: {"t", "seq", "src": "sampler", "state": "dark", "luma": f}
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path


def iso_utc(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat(timespec="seconds")


def slim(pots):
    out = []
    for p in pots:
        rec = {"s": p["side"], "h": p["h"], "e": p["e"], "d": p["d"], "ml": round(p["ml"], 1)}
        if "u" in p:
            rec["u"] = p["u"]
            rec["v"] = p["v"]
        if p.get("agree") is not None:
            rec["a"] = p["agree"]           # ml of disagreement with the previous reading
        # filter output, present only when the service runs the filter
        for src_key, dst in (("temp_c", "t_c"), ("f_ml", "fm"), ("f_lo", "flo"), ("f_hi", "fhi")):
            if p.get(src_key) is not None:
                rec[dst] = p[src_key]
        out.append(rec)
    return out


class ReadingsStore:
    def __init__(self, pattern: str, clock, flush_sec: float = 60.0,
                 latest_path: str | None = None):
        self.pattern = pattern
        self.clock = clock
        self.flush_sec = flush_sec
        self.latest_path = Path(latest_path) if latest_path else None
        self.buf: list[str] = []
        self.last_flush_mono = clock.mono()
        self.bad_records = 0
        self.appends = 0
        self.records = 0
        self.latest = {"seq": -1, "t": None, "last_usable_seq": -1, "last_usable_t": None,
                       "records_today": 0, "day": None}

    def path_for(self, wall: float) -> Path:
        return Path(datetime.fromtimestamp(wall).strftime(self.pattern))

    def add(self, rec: dict, usable: bool = False) -> None:
        try:
            line = json.dumps(rec, allow_nan=False, separators=(",", ":"))
        except ValueError:
            self.bad_records += 1
            return
        self.buf.append(line)
        self.records += 1
        day = rec["t"][:10]
        if self.latest["day"] != day:
            self.latest["day"] = day
            self.latest["records_today"] = 0
        self.latest["records_today"] += 1
        self.latest["seq"] = rec.get("seq", -1)
        self.latest["t"] = rec["t"]
        if usable:
            self.latest["last_usable_seq"] = rec.get("seq", -1)
            self.latest["last_usable_t"] = rec["t"]

    def flush(self, force: bool = False) -> bool:
        now = self.clock.mono()
        if not force and now - self.last_flush_mono < self.flush_sec:
            return False
        self.last_flush_mono = now
        if not self.buf:
            return False
        path = self.path_for(self.clock.wall())
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a", encoding="utf-8") as fh:
                fh.write("\n".join(self.buf) + "\n")
            self.appends += 1
            self.buf.clear()
        except OSError:
            return False
        self._write_latest()
        return True

    def _write_latest(self) -> None:
        if self.latest_path is None:
            return
        tmp = self.latest_path.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(self.latest), encoding="utf-8")
            os.replace(tmp, self.latest_path)
        except OSError:
            pass
