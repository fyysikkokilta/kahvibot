"""Pi entry point: python run_daemon.py --model-dir /home/konsta/coffee-reader ...

Replaces sampler.py as kahvisampler.service's ExecStart. Same camera arguments,
same log location; adds the IPC socket the bot talks to.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.camera import FswebcamCamera          # noqa: E402
from pipeline.clock import RealClock                # noqa: E402
from pipeline.gate import Gate                      # noqa: E402
from pipeline.graphing import load_kahvibot_graphs  # noqa: E402
from pipeline.ipc import serve_forever              # noqa: E402
from pipeline.reader import WarmReader              # noqa: E402
from pipeline.service import ReaderService, ServiceConfig  # noqa: E402
from pipeline.store import ReadingsStore            # noqa: E402


def _read_secret(path: str) -> str:
    """Read a password from a file. Command lines are world-readable in ps, and
    this one is in a systemd unit anyone can cat."""
    if not path:
        return ""
    try:
        return Path(path).read_text(encoding="utf-8").strip()
    except OSError:
        logging.getLogger("kahvi").warning("could not read %s; connecting without a password", path)
        return ""


def main(argv=None) -> int:
    here = Path(__file__).resolve().parent
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model-dir", default=str(here.parent))
    ap.add_argument("--log", default=None, help="readings JSONL strftime pattern")
    ap.add_argument("--run-dir", default=os.environ.get("RUNTIME_DIRECTORY", "/run/kahvi-sampler"))
    ap.add_argument("--lock", default="/run/lock/kahvicam.lock")
    ap.add_argument("--socket", default=None, help="AF_UNIX path (default <run-dir>/ipc.sock) or TCP port")
    ap.add_argument("--graphs", default="/home/marci/dev/kiltiskahvi/graphs.py")
    ap.add_argument("--interval", type=float, default=10.0)
    ap.add_argument("--dark-interval", type=float, default=60.0)
    ap.add_argument("--detect-every", type=int, default=6)
    ap.add_argument("--tta-probe-every", type=int, default=0)
    ap.add_argument("--reuse-max-age", type=float, default=15.0)
    ap.add_argument("--gate-ok", type=float, default=0.62, help="entropy tier limit (fallback / entropy mode)")
    ap.add_argument("--gate-uncertain", type=float, default=0.68)
    ap.add_argument("--gate-mode", default="agree", choices=["entropy", "agree"],
                    help="agree: a reading is ok when it agrees with the previous one of the same pot "
                         "(gym/GATE3_*.md); entropy is only the fallback without a recent neighbour")
    ap.add_argument("--agree-ok-ml", type=float, default=40.0)
    ap.add_argument("--agree-uncertain-ml", type=float, default=90.0)
    ap.add_argument("--threads", type=int, default=2)
    ap.add_argument("--filter", action="store_true",
                    help="run the (volume, temperature) filter; needs a bundle with line_logits")
    ap.add_argument("--filter-particles", type=int, default=800)
    ap.add_argument("--mqtt-host", default="127.0.0.1")
    ap.add_argument("--mqtt-port", type=int, default=1883)
    ap.add_argument("--mqtt-user", default="")
    ap.add_argument("--mqtt-password-file", default="",
                    help="file holding the broker password; never pass it on the command line")
    ap.add_argument("--mqtt-base-topic", default="zigbee2mqtt")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(levelname)s %(message)s")

    model_dir = Path(a.model_dir)
    run_dir = Path(a.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    log_pattern = a.log or str(model_dir / "readings-%Y-%m.jsonl")
    sock = a.socket or str(run_dir / "ipc.sock")
    if sock.isdigit():
        sock = int(sock)

    clock = RealClock()
    camera = FswebcamCamera(clock, lock_path=a.lock, tmp_path=str(run_dir / "frame.jpg"))
    reader = WarmReader(model_dir, threads=a.threads)
    # latest.json belongs beside the readings, not inside the model bundle: the
    # bundle is a checkout of the repository and must stay clean.
    store = ReadingsStore(log_pattern, clock,
                          latest_path=str(Path(log_pattern).parent / "latest.json"))
    graphs_mod = None
    if a.graphs and Path(a.graphs).is_file():
        try:
            graphs_mod = load_kahvibot_graphs(a.graphs)
        except Exception:  # noqa: BLE001
            logging.getLogger("kahvi").warning("graphs module unavailable", exc_info=True)
    cfg = ServiceConfig(interval=a.interval, dark_interval=a.dark_interval,
                        detect_every=a.detect_every, tta_probe_every=a.tta_probe_every,
                        reuse_max_age=a.reuse_max_age,
                        filter_enabled=a.filter, filter_particles=a.filter_particles,
                        calibration_path=str(model_dir / "calibration.json"),
                        mqtt_host=a.mqtt_host, mqtt_port=a.mqtt_port,
                        mqtt_user=a.mqtt_user, mqtt_password=_read_secret(a.mqtt_password_file),
                        mqtt_base_topic=a.mqtt_base_topic)
    gate = Gate(a.gate_ok, a.gate_uncertain, mode=a.gate_mode,
                agree_ok_ml=a.agree_ok_ml, agree_unc_ml=a.agree_uncertain_ml)
    svc = ReaderService(camera, reader, store, clock, gate, cfg, graphs_mod=graphs_mod)
    # Recover today's readings from the log. Without this a restart or a power
    # cut makes /graph answer "not enough readings yet" for an hour, even though
    # the whole day is already on disk in the file this service wrote.
    try:
        now = clock.wall()
        seeded = svc.daybuf.seed_from_log(store.path_for(now), now)
        if seeded:
            logging.getLogger("kahvi").info("recovered %d of today's readings from %s",
                                            seeded, store.path_for(now))
    except Exception:  # noqa: BLE001
        logging.getLogger("kahvi").warning("could not recover today's readings", exc_info=True)
    logging.getLogger("kahvi").info("reader service up: interval=%.0fs socket=%s gate=%s e<=%.2f/%.2f a<=%.0f/%.0f ml",
                                    a.interval, sock, a.gate_mode, a.gate_ok, a.gate_uncertain,
                                    a.agree_ok_ml, a.agree_uncertain_ml)
    serve_forever(svc, sock)
    return 0


if __name__ == "__main__":
    sys.exit(main())
