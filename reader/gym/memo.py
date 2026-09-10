"""Memoising reader for the gym: the archive has one frame per ~5 min while the
sampler ticks every 10 s, so the same frame is read many times. Results and
the local compute time of the first real run are replayed, so both readings
and charged costs stay identical to a non-memoised run."""
from __future__ import annotations

import copy


class MemoReader:
    def __init__(self, reader):
        self.r = reader
        self.detect_memo: dict = {}
        self.read_memo: dict = {}
        self.hits = 0
        self.misses = 0
        self.local_seconds = 0.0    # includes replayed costs

    # attributes the service touches
    @property
    def n_detect(self):
        return self.r.n_detect

    @property
    def n_read(self):
        return self.r.n_read

    @property
    def n_views(self):
        return self.r.n_views

    @staticmethod
    def _bkey(dets):
        return tuple((d["side"], tuple(round(v, 1) for v in d["box"])) for d in dets)

    def detect_timed(self, rgb, ident=None):
        key = ident
        if key is not None and key in self.detect_memo:
            dets, dt = self.detect_memo[key]
            self.hits += 1
            self.local_seconds += dt
            return copy.deepcopy(dets), dt
        dets, dt = self.r.detect_timed(rgb)
        self.misses += 1
        self.local_seconds += dt
        if key is not None:
            self.detect_memo[key] = (copy.deepcopy(dets), dt)
        return dets, dt

    def read_pots(self, rgb, dets, tta_views=1, ident=None):
        key = (ident, self._bkey(dets), tta_views) if ident is not None else None
        if key is not None and key in self.read_memo:
            pots, dt = self.read_memo[key]
            self.hits += 1
            self.local_seconds += dt
            return copy.deepcopy(pots), dt
        pots, dt = self.r.read_pots(rgb, dets, tta_views)
        self.misses += 1
        self.local_seconds += dt
        if key is not None:
            self.read_memo[key] = (copy.deepcopy(pots), dt)
        return pots, dt
