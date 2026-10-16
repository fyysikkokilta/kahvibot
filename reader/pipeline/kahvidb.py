"""Import into and export from the store (store.py).

  python -m pipeline.kahvidb import-readings DB readings-2026-09.jsonl ...
  python -m pipeline.kahvidb import-power   DB vasen power_vasen.csv
  python -m pipeline.kahvidb import-brews   DB vasen brews_vasen.jsonl
  python -m pipeline.kahvidb export-readings DB [--since 2026-10-01] > readings.jsonl
  python -m pipeline.kahvidb export-power    DB [--since ...]        > power.csv
  python -m pipeline.kahvidb export-brews    DB                      > brews.csv
  python -m pipeline.kahvidb stats DB

The imports read the formats the Pi wrote before the store existed (the
service's readings JSONL, the power logger's CSV and brews JSONL) and are
idempotent: a row already present is skipped, so a rerun after a partial
import is safe. The exports write the same JSONL the gym replays.

Run the imports while the service is stopped: the service is the store's only
writer, and that is the point of having one.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from pipeline.store import connect, epoch_of  # noqa: E402
else:
    from .store import connect, epoch_of


def _since(s):
    if not s:
        return 0.0
    return datetime.fromisoformat(s).astimezone().timestamp()


def import_readings(conn, paths) -> int:
    seen = {r for r in conn.execute("SELECT t, seq FROM readings")}
    rows = []
    for path in paths:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    t = epoch_of(rec["t"])
                except (ValueError, KeyError, TypeError, AttributeError):
                    continue                    # a truncated line from a power cut
                key = (t, rec.get("seq"))
                if key in seen:
                    continue
                seen.add(key)
                rows.append((t, rec.get("seq"), rec.get("src"),
                             json.dumps(rec, separators=(",", ":"))))
    with conn:
        conn.executemany("INSERT INTO readings (t, seq, src, rec) VALUES (?, ?, ?, ?)", rows)
    return len(rows)


def import_power(conn, device, path) -> int:
    seen = {t for (t,) in conn.execute("SELECT t FROM power WHERE device = ?", (device,))}
    rows = []
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            try:
                t, w = epoch_of(row["timestamp"]), float(row["power"])
            except (ValueError, KeyError, TypeError):
                continue
            if t not in seen:
                seen.add(t)
                rows.append((t, device, w))
    with conn:
        conn.executemany("INSERT INTO power (t, device, watts) VALUES (?, ?, ?)", rows)
    return len(rows)


def import_brews(conn, device, path) -> int:
    n = 0
    with conn, open(path, encoding="utf-8") as fh:
        for line in fh:
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            if ev.get("event") != "end":
                continue                        # every start has its end line
            cur = conn.execute("INSERT OR IGNORE INTO brews (device, start, end, peak_w) "
                               "VALUES (?, ?, ?, ?)",
                               (device, epoch_of(ev["start"]), epoch_of(ev["end"]), ev.get("peak_w")))
            n += cur.rowcount
    return n


def export_readings(conn, since, out) -> int:
    n = 0
    for (line,) in conn.execute("SELECT rec FROM readings WHERE t >= ? ORDER BY t", (since,)):
        out.write(line + "\n")
        n += 1
    return n


def export_power(conn, since, out) -> int:
    w = csv.writer(out)
    w.writerow(["timestamp", "device", "power"])
    n = 0
    for t, dev, watts in conn.execute("SELECT t, device, watts FROM power WHERE t >= ? ORDER BY t",
                                      (since,)):
        w.writerow([datetime.fromtimestamp(t).astimezone().isoformat(), dev, watts])
        n += 1
    return n


def export_brews(conn, since, out) -> int:
    w = csv.writer(out)
    w.writerow(["device", "start", "end", "duration_s", "peak_w"])
    n = 0
    for dev, start, end, peak in conn.execute(
            "SELECT device, start, end, peak_w FROM brews WHERE start >= ? ORDER BY start", (since,)):
        iso = lambda t: "" if t is None else datetime.fromtimestamp(t).astimezone().isoformat()  # noqa: E731
        w.writerow([dev, iso(start), iso(end), "" if end is None else round(end - start, 1), peak])
        n += 1
    return n


def stats(conn) -> dict:
    out = {}
    for table in ("readings", "power", "brews", "filter_state"):
        n, lo, hi = conn.execute(
            f"SELECT count(*), min({'start' if table == 'brews' else 't'}), "
            f"max({'start' if table == 'brews' else 't'}) FROM {table}").fetchone()
        fmt = lambda t: None if t is None else datetime.fromtimestamp(t).astimezone().isoformat(timespec="seconds")  # noqa: E731
        out[table] = {"rows": n, "first": fmt(lo), "last": fmt(hi)}
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("import-readings"); p.add_argument("db"); p.add_argument("files", nargs="+")
    for name in ("import-power", "import-brews"):
        p = sub.add_parser(name); p.add_argument("db"); p.add_argument("device"); p.add_argument("file")
    for name in ("export-readings", "export-power", "export-brews"):
        p = sub.add_parser(name); p.add_argument("db"); p.add_argument("--since", default="")
    p = sub.add_parser("stats"); p.add_argument("db")
    a = ap.parse_args(argv)

    readonly = a.cmd.startswith("export") or a.cmd == "stats"
    conn = connect(a.db, readonly=readonly)
    if a.cmd == "import-readings":
        n = import_readings(conn, a.files)
    elif a.cmd == "import-power":
        n = import_power(conn, a.device, a.file)
    elif a.cmd == "import-brews":
        n = import_brews(conn, a.device, a.file)
    elif a.cmd == "export-readings":
        n = export_readings(conn, _since(a.since), sys.stdout)
    elif a.cmd == "export-power":
        n = export_power(conn, _since(a.since), sys.stdout)
    elif a.cmd == "export-brews":
        n = export_brews(conn, _since(a.since), sys.stdout)
    else:
        print(json.dumps(stats(conn), indent=2))
        return 0
    print(f"{a.cmd}: {n} rows", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
