"""Single-writer store: one SQLite file for everything the Pi measures.

Readings, plug power, brews and the filter's state all land in one database
that only the reader service writes. Before this there were three writers and
four formats (the service's JSONL, the bot's own JSONL, the power logger's CSV
and its brews JSONL), and every consumer parsed its own file.

Writes are batched per flush interval (SAMPLER.md §6) so the SD card sees one
transaction a minute, not one per reading. WAL with synchronous=NORMAL keeps
the file consistent across a power cut -- the last uncommitted batch is lost,
nothing older -- which matters on a Pi whose 5 V rail sags.

Record schema (rec column, every lit frame, whoever asked for it):
  {"t": iso-utc, "seq": n, "src": "sampler"|"bot", "luma": f,
   "pots": [{"s": side, "h": f, "e": f, "d": f, "ml": f}], "tta": n?}
Dark ticks: {"t", "seq", "src": "sampler", "state": "dark", "luma": f}

The bot and the health check open the file read-only (connect(readonly=True)).
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS readings (
    t    REAL NOT NULL,          -- epoch seconds, UTC
    seq  INTEGER,
    src  TEXT,
    rec  TEXT NOT NULL           -- the record as JSON, schema above
);
CREATE INDEX IF NOT EXISTS readings_t ON readings (t);
CREATE TABLE IF NOT EXISTS power (
    t      REAL NOT NULL,
    device TEXT NOT NULL,
    watts  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS power_device_t ON power (device, t);
CREATE TABLE IF NOT EXISTS brews (
    device TEXT NOT NULL,
    start  REAL NOT NULL,
    end    REAL,                 -- NULL while the brew is running
    peak_w REAL,
    PRIMARY KEY (device, start)
);
CREATE TABLE IF NOT EXISTS filter_state (
    side  TEXT PRIMARY KEY,
    t     REAL NOT NULL,
    state BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS meta (
    k TEXT PRIMARY KEY,
    v TEXT
);
"""


def iso_utc(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat(timespec="seconds")


def epoch_of(iso: str) -> float:
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def connect(path, readonly: bool = False, timeout: float = 5.0) -> sqlite3.Connection:
    """Open the database. Read-only connections never create or migrate it."""
    if readonly:
        conn = sqlite3.connect(f"file:{Path(path).as_posix()}?mode=ro", uri=True,
                               timeout=timeout, check_same_thread=False)
        return conn
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=timeout, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.executescript(SCHEMA)
    conn.execute("INSERT OR REPLACE INTO meta (k, v) VALUES ('schema', ?)", (str(SCHEMA_VERSION),))
    conn.commit()
    return conn


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
    """Buffers rows in memory and commits them in one transaction per flush.

    Thread-safe: the MQTT thread adds power rows while the loop thread adds
    readings, and one connection behind one lock serves both. A brew event
    marks the buffer urgent so it is on disk by the next loop pass, because
    the bot's "brewing now" line reads it from there.
    """

    def __init__(self, path, clock, flush_sec: float = 60.0):
        self.path = str(path)
        self.clock = clock
        self.flush_sec = flush_sec
        self.conn = connect(self.path)
        self._lock = threading.Lock()
        self._readings: list[tuple] = []
        self._power: list[tuple] = []
        self._brews: list[tuple] = []        # (sql, params) upserts, in order
        self.urgent = False
        self.last_flush_mono = clock.mono()
        self.bad_records = 0
        self.appends = 0
        self.records = 0
        self.latest = {"seq": -1, "t": None, "last_usable_seq": -1, "last_usable_t": None,
                       "records_today": 0, "day": None}

    # -- writes (buffered) ------------------------------------------------------
    def add(self, rec: dict, usable: bool = False) -> None:
        try:
            line = json.dumps(rec, allow_nan=False, separators=(",", ":"))
        except ValueError:
            self.bad_records += 1
            return
        with self._lock:
            self._readings.append((epoch_of(rec["t"]), rec.get("seq"), rec.get("src"), line))
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

    def add_power(self, device: str, wall: float, watts: float) -> None:
        with self._lock:
            self._power.append((wall, device, float(watts)))

    def add_brew(self, device: str, event: dict) -> None:
        """A BrewTracker event: 'start' inserts the brew, 'end' closes it."""
        with self._lock:
            if event["event"] == "start":
                self._brews.append(("INSERT OR IGNORE INTO brews (device, start, peak_w) "
                                    "VALUES (?, ?, ?)", (device, event["start"], event["peak_w"])))
            else:
                self._brews.append(("INSERT INTO brews (device, start, end, peak_w) VALUES (?, ?, ?, ?) "
                                    "ON CONFLICT (device, start) DO UPDATE SET end = excluded.end, "
                                    "peak_w = excluded.peak_w",
                                    (device, event["start"], event["end"], event["peak_w"])))
            self.urgent = True

    def save_filter(self, side: str, wall: float, blob: bytes) -> None:
        with self._lock:
            self.conn.execute("INSERT OR REPLACE INTO filter_state (side, t, state) VALUES (?, ?, ?)",
                              (side, wall, sqlite3.Binary(blob)))
            self.conn.commit()

    def flush(self, force: bool = False) -> bool:
        now = self.clock.mono()
        if not force and not self.urgent and now - self.last_flush_mono < self.flush_sec:
            return False
        self.last_flush_mono = now
        with self._lock:
            if not (self._readings or self._power or self._brews):
                self.urgent = False
                return False
            try:
                with self.conn:                     # one transaction
                    self.conn.executemany("INSERT INTO readings (t, seq, src, rec) VALUES (?, ?, ?, ?)",
                                          self._readings)
                    self.conn.executemany("INSERT INTO power (t, device, watts) VALUES (?, ?, ?)",
                                          self._power)
                    for sql, params in self._brews:
                        self.conn.execute(sql, params)
            except sqlite3.Error:
                return False                        # keep the buffer; retry next pass
            self._readings.clear()
            self._power.clear()
            self._brews.clear()
            self.urgent = False
        self.appends += 1
        return True

    # -- reads (the writer's own view) -------------------------------------------
    def records_since(self, wall: float) -> list[dict]:
        with self._lock:
            rows = self.conn.execute("SELECT rec FROM readings WHERE t >= ? ORDER BY t", (wall,)).fetchall()
        out = []
        for (line,) in rows:
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
        return out

    def power_since(self, wall: float) -> list[tuple]:
        with self._lock:
            return self.conn.execute("SELECT device, t, watts FROM power WHERE t >= ? ORDER BY t",
                                     (wall,)).fetchall()

    def load_filters(self) -> dict:
        with self._lock:
            return {side: (t, bytes(blob)) for side, t, blob in
                    self.conn.execute("SELECT side, t, state FROM filter_state")}

    def close(self) -> None:
        self.flush(force=True)
        with self._lock:
            self.conn.close()


# -- read side, for the bot and the health check ------------------------------

def last_brew(conn: sqlite3.Connection, device: str):
    """(start, end) epoch seconds of the newest brew; end is None while brewing."""
    return conn.execute("SELECT start, end FROM brews WHERE device = ? ORDER BY start DESC LIMIT 1",
                        (device,)).fetchone()


def last_reading_t(conn: sqlite3.Connection):
    row = conn.execute("SELECT max(t) FROM readings").fetchone()
    return row[0] if row else None
