"""Integration test: real model + archive camera + real clock, served over the
IPC socket (loopback TCP on Windows, AF_UNIX on the Pi), consumed through
ReaderClient exactly as kahvibot will. Skips if the model or archive is absent."""
from __future__ import annotations

import queue
import sys
import tempfile
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gym.paths import ARCHIVE, KAHVIBOT  # noqa: E402

MODEL_DIR = Path(__file__).resolve().parents[1] / "models"   # the deployed bundle


@pytest.mark.skipif(not (MODEL_DIR / "reader.onnx").exists() or not ARCHIVE.is_dir(), reason="model/archive missing")
def test_client_roundtrip():
    from pipeline.botclient import ReaderClient
    from pipeline.camera import ArchiveCamera
    from pipeline.clock import RealClock
    from pipeline.gate import Gate
    from pipeline.graphing import load_kahvibot_graphs
    from pipeline.ipc import IPCServer, execute
    from pipeline.reader import WarmReader
    from pipeline.service import ReaderService, ServiceConfig
    from pipeline.store import ReadingsStore
    from gym.archive import FrameArchive

    archive = FrameArchive([ARCHIVE])
    clock = RealClock()
    # archive camera on the real clock: pretend "now" is the densest archive day
    day = archive.densest_days(1)[0][0]

    class DayCamera(ArchiveCamera):
        def capture(self):
            fr = super().capture()
            return fr
    cam = ArchiveCamera(archive, clock, capture_cost_s=0.0)
    # steer frame lookup to the archive day by offsetting the wall time
    import datetime as _dt
    offset = _dt.datetime(day.year, day.month, day.day, 12, 0).timestamp() - time.time()
    cam.src.frame_at = (lambda orig: (lambda wall, mono: orig(wall + offset, mono)))(cam.src.frame_at)

    tmp = Path(tempfile.mkdtemp())
    store = ReadingsStore(str(tmp / "r-%Y-%m.jsonl"), clock, flush_sec=1.0, latest_path=str(tmp / "latest.json"))
    graphs = KAHVIBOT / "graphs.py"
    gmod = load_kahvibot_graphs(graphs) if graphs.exists() else None
    svc = ReaderService(cam, WarmReader(MODEL_DIR, threads=2), store, clock, Gate(0.62, 0.68),
                        ServiceConfig(interval=2.0, reuse_max_age=5.0), graphs_mod=gmod)
    svc.run_due()                       # one tick now

    inbox = queue.Queue()
    server = IPCServer(("127.0.0.1", 0), inbox)
    port = server.sock.getsockname()[1]
    server.start()
    stop = threading.Event()

    def loop():
        while not stop.is_set():
            try:
                req = inbox.get(timeout=0.1)
            except queue.Empty:
                svc.run_due()
                continue
            execute(svc, req)
    t = threading.Thread(target=loop, daemon=True)
    t.start()
    try:
        rc = ReaderClient(("127.0.0.1", port), timeout=20.0)
        assert rc.alive()["ok"]
        got = rc.photo(max_age=5.0)
        assert got is not None
        jpeg, pots, meta = got
        assert jpeg[:2] == b"\xff\xd8" and isinstance(pots, list) and meta["reused"] in (True, False)
        if pots:
            assert {"side", "h", "e", "ml", "tier"} <= set(pots[0])
        png, caption = rc.graph()
        assert caption is not None
    finally:
        stop.set()
        server.stop.set()
        server.sock.close()
