# reader — the coffee level reader

Everything the Pi needs to turn a webcam frame into millilitres, and the gym that
checks it against archived frames before anything is deployed.

| path | what |
|---|---|
| `read_frame.py` | The reader itself: carafe detector (`fastbox.onnx`), surface model (`reader.onnx`), calibration `h_norm -> ml`. ONNX Runtime + numpy + Pillow, no torch. `python read_frame.py --model-dir models frame.jpg` prints the reading as JSON. |
| `models/` | The deployed model bundle (v8). The `.onnx.data` weight files must sit beside their `.onnx`. |
| `pipeline/` | The resident reader service (`run_daemon.py`, `kahvi-reader.service`): one process owns the camera and the warm model, samples every 10 s, writes the readings JSONL, answers the bot over a local socket (a fresh frame plus reading, or today's graph) and gates readings on agreement between consecutive frames. Design, benchmark and deployment: `PIPELINE.md`. Tests: `cd reader && python -m pytest pipeline`. |
| `install_reader.sh` | Idempotent install/upgrade on the Pi; replaces the old `kahvisampler.service`. |
| `sampler/` | The previous background sampler (deployed 2026-08, superseded by `pipeline/`). Kept for reference until the service has run in the field. |
| `gym/` | Simulator and benchmarks: replays archived frames through the legacy and streamlined pipelines on a Pi-cost virtual clock, scores model checkpoints on blind hand clicks and field clicks, evaluates gates. Needs the research data (see `gym/paths.py`); results are committed as `gym/BENCH*.md`, `gym/MODELS.md`, `gym/GATE*.md`. |

Training code, labels, the frame archive and checkpoints live in the separate
`coffee_mesh_pred` research checkout; this directory only carries what runs on the
Pi and what is needed to reproduce the reports.
