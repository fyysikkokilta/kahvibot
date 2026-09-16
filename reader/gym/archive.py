"""Index of archived frames by capture time (file names are local time)."""
from __future__ import annotations

import bisect
import collections
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, Optional

STAMP = re.compile(r"(\d{4})-(\d{2})-(\d{2})_(\d{2})-(\d{2})-(\d{2})")


@dataclass(frozen=True)
class ArchiveFrame:
    stem: str
    path: Path
    epoch: float

    def read(self) -> bytes:
        return self.path.read_bytes()


class FrameArchive:
    def __init__(self, dirs: Iterable[str | Path], prefix: str = "coffee_2026"):
        frames: dict[str, ArchiveFrame] = {}
        for d in dirs:
            d = Path(d)
            if not d.is_dir():
                continue
            for p in d.iterdir():
                if p.suffix.lower() != ".jpg" or not p.name.startswith(prefix):
                    continue
                m = STAMP.search(p.stem)
                if not m:
                    continue
                y, mo, da, h, mi, s = map(int, m.groups())
                epoch = datetime(y, mo, da, h, mi, s).timestamp()
                stem = p.stem[-19:]
                frames.setdefault(stem, ArchiveFrame(stem, p, epoch))
        self.frames = sorted(frames.values(), key=lambda f: f.epoch)
        self.epochs = [f.epoch for f in self.frames]

    def __len__(self):
        return len(self.frames)

    def nearest(self, epoch: float) -> Optional[ArchiveFrame]:
        if not self.frames:
            return None
        i = bisect.bisect_left(self.epochs, epoch)
        cands = [j for j in (i - 1, i) if 0 <= j < len(self.frames)]
        return min((self.frames[j] for j in cands), key=lambda f: abs(f.epoch - epoch))

    def on_day(self, day: date) -> list[ArchiveFrame]:
        t0 = datetime(day.year, day.month, day.day).timestamp()
        t1 = t0 + 86400
        i0, i1 = bisect.bisect_left(self.epochs, t0), bisect.bisect_left(self.epochs, t1)
        return self.frames[i0:i1]

    def per_day(self) -> collections.Counter:
        return collections.Counter(datetime.fromtimestamp(f.epoch).date() for f in self.frames)

    def densest_days(self, n: int = 5) -> list[tuple[date, int]]:
        return self.per_day().most_common(n)

    def consecutive_run(self, n_days: int) -> list[date]:
        """The n consecutive days with the most frames in total."""
        pd = self.per_day()
        days = sorted(pd)
        best, best_sum = None, -1
        for start in days:
            run = [date.fromordinal(start.toordinal() + k) for k in range(n_days)]
            s = sum(pd.get(d, 0) for d in run)
            if s > best_sum:
                best, best_sum = run, s
        return best or []
