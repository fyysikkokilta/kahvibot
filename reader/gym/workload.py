"""Request timelines. Real ones come from the bot's own photo records in the
Pi readings log (no chat content involved); synthetic ones for stress."""
from __future__ import annotations

import json
import random
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

TZ = timezone(timedelta(hours=3))


def bot_photo_times(readings_paths: Iterable[str | Path]) -> list[datetime]:
    """Local datetimes of every bot-triggered photo in the readings JSONL."""
    out = []
    for p in readings_paths:
        p = Path(p)
        if not p.is_file():
            continue
        for line in p.open(encoding="utf-8"):
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("src") == "sampler":
                continue
            s = r.get("captured_at") or r.get("read_at")
            if s:
                out.append(datetime.fromisoformat(s).astimezone(TZ))
    return sorted(out)


def by_day(times: list[datetime]) -> dict[date, list[float]]:
    """day -> seconds since local midnight for each request."""
    out: dict[date, list[float]] = {}
    for t in times:
        out.setdefault(t.date(), []).append(t.hour * 3600 + t.minute * 60 + t.second)
    return out


def on_day(seconds_of_day: list[float], day: date) -> list[float]:
    base = datetime(day.year, day.month, day.day).timestamp()
    return sorted(base + s for s in seconds_of_day)


def poisson(rate_per_hour: float, start_epoch: float, end_epoch: float, seed: int = 0) -> list[float]:
    rng = random.Random(seed)
    t, out = start_epoch, []
    while True:
        t += rng.expovariate(rate_per_hour / 3600.0)
        if t >= end_epoch:
            return out
        out.append(t)


def burst(start_epoch: float, n: int, gap_s: float) -> list[float]:
    return [start_epoch + i * gap_s for i in range(n)]


def graph_calls(request_epochs: list[float], every: int = 6, offset_s: float = 20.0) -> list[float]:
    """Model /graph as every Nth photo request, a little after it (FK Lörs:
    32 graph calls per 211 triggers, ~1 in 6)."""
    return [t + offset_s for i, t in enumerate(request_epochs) if i % every == every - 1]
