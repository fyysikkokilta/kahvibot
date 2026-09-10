# gym — replay the guild room on this laptop

> **Location note.** This code lives in `reader/gym/` of the kahvibot repo and runs from `reader/`
> (`cd reader && python -m gym.bench --quick`). The data it needs (frame archive, `_work/` labels,
> caches and checkpoints) is not in this repo: set `COFFEE_RESEARCH_DIR` to the `coffee_mesh_pred`
> research checkout (default: a sibling directory of that name). See `gym/paths.py`.

Three harnesses, one idea: the frame archive (10 099 kahvibot frames, Jan–Jun 2026,
`raw_img/`) plus the Pi's own request log stand in for the guild room, real
inference runs on real frames, and time is virtual but anchored to what the Pi
measured. Run everything from `coffee_mesh_pred/`.

| script | question it answers | output |
|---|---|---|
| `python -m coffee10.gym.bench` | legacy vs streamlined pipeline: latency, captures, CPU, coverage, graph cache, under real request timelines | `BENCH.md`, `bench_results.json` |
| `python -m coffee10.gym.models --candidates tag=ckpt ...` | which reader checkpoint to deploy: blind hand-click accuracy, field accuracy, coverage at gates, what each gate keeps | `BENCH_MODELS*.md` |
| `python -m coffee10.gym.gate2 --model-dir _work/onnx_<tag>` | does entropy (or a learned score) actually separate accurate readings from bad ones | `GATE2_<tag>.md` |

## Pieces

* `archive.py` — frames indexed by capture time; nearest-frame lookup.
* `workload.py` — request timelines from the Pi readings (bot photo times, all
  chats, no chat content), Poisson and burst generators, /graph as every 6th call.
* `costs.py` — the Pi 3B cost model. Anchors: 8 s detect+TTA8 read (measured),
  33 s legacy sampler cadence under the 25 % quota (measured), 2 s fswebcam.
  Assumptions are labelled in the file and repeated in every report.
* `memo.py` — memoised reader so a 10 s tick against a 5-minute archive costs
  one inference per frame, with the first run's local time replayed.
* `legacy.py` — discrete-event model of kahvibot + sampler.py as deployed.
* `sim.py` — the streamlined `pipeline.ReaderService` on a `VirtualClock`.
* `bench.py`, `models.py`, `gate2.py` — the three entry points above.

## Field set

`_work/field_frames/` (208 frames from kahviraspi 2026-08-29..09-09: the survey
cache plus the bot's own posts fetched from Telegram), boxed with fastbox into
`_work/field_320x160.npy` + `_work/field_meta.json`. `_work/hand_lines_field.json`
holds 34 pots with human surface clicks converted from the survey's
`tg_clicks.jsonl` (31 with a visible surface), blind split in
`_work/hand_blind_field.json` with the survey's salt. This is the only labelled
data from the deployed camera; it is evaluation-only.

## Reading the numbers

* Latencies include an assumed 3 s Telegram upload in both designs.
* "Pi-projected" = local seconds × scale, scale = 8.0 / local detect+TTA8 time.
* Errors against clicks are |Δh|·1250 ml on the linear scale; a single click
  carries ~21 ml of noise (coffee10/README.md §8.3), so differences under ~10 ml
  between models on n≈30–100 records are not differences.
* Coverage is the share of pots a gate would show. A gate is only worth its
  coverage cost if the kept readings are more accurate than the rejected ones
  (`models.py` §3, `gate2.py`).
