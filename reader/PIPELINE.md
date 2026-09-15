# One reader — the streamlined kahvibot pipeline

Status: implemented in `reader/pipeline/`, benchmarked in `reader/gym/` (both in the kahvibot repo; originally `coffee10/` in the research checkout)
(see `gym/BENCH.md`), not yet deployed. Companion to SAMPLER.md and GRAPHS.md;
the field evidence it answers is in `coffee/kahviraspi_logs_2026-09-09/ANALYSIS.md`.

## 0. What the field logs said

Twelve days of kahviraspi (2026-08-29 → 09-09):

* every `/status` waited **≈13 s** for a photo: fswebcam ~2 s, then a cold
  `read_frame.py` subprocess (python + onnxruntime + TTA=8) ~8 s, then upload;
* the sampler configured for 10 s ran at **33 s** because of `CPUQuota=25%`, and
  spent 27 % of lit time in a 60 s backoff triggered by "no ok reading" — which,
  given the gate, means "there is coffee in the carafe";
* two independent processes read the same camera with the same model, one warm
  and one cold, and wrote two record schemas to one file as two users;
* the `/graph` cache keyed on the log's mtime never hit;
* the ok gate (`entropy ≤ 0.55`) passed 25–30 % of pots and almost only empty ones.

## 1. Design

One resident process, `ReaderService`, owns the camera and the model:

```
 kahvibot ──/run/kahvi-sampler/ipc.sock──▶ ReaderService ──▶ readings-%Y-%m.jsonl
   │  {"op":"frame","max_age":15}            │  tick every 10 s          latest.json
   │  {"op":"graph"}                         │  capture → luma → detect/6 → read TTA=1
   │  {"op":"ping"}                          │  requests served between ticks
   └─ fallback: fswebcam, no reading         └─ graph rendered from the in-memory day
```

* **frame(max_age)** — if the last lit frame is younger than `max_age` (15 s) it
  is returned at once with its reading; otherwise the service captures now,
  reads it (TTA=1, cached box) and records it as `src: bot`. A bot frame is a
  sample too, so it pushes the next tick out one interval.
* **Photo-first** — the frame is usable as soon as capture finishes; the reading
  follows ~1–2 s later on the Pi. The bot sends the photo, then edits the caption.
* **Fallback** — any socket error, timeout (3 s) or `ok:false` and the bot does
  exactly what it does today. The service can be stopped at any time.
* **Single writer, one schema** — only the service appends:
  `{"t","seq","src","luma","pots":[{"s","h","e","d","ml"}]}`. Millilitres are
  always written; `ok` is not in the record.
* **Gate downstream** (`gate.py`) — the reader always writes `h`, `e`, `ml`
  and, new, `a`: the millilitres by which the reading disagrees with the
  previous reading of the same pot when that is under 60 s old. Default mode
  `agree`: `ok` when `a ≤ 40 ml`, `uncertain` when `a ≤ 90 ml`, else abstain;
  entropy (`e ≤ 0.62 / 0.68`) only decides when no recent neighbour exists.
  Config values, validated on the archive, not a model redeploy. Evidence in §2b.
* **Graph** (`graphing.py`) — cache key `(local date, seq of last usable reading)`
  with a 10 min TTL; rendered from the day buffer, never re-parsing the log.
* **Blind backoff** on "no carafe detected", never on abstention. No TTA probes.
* **IPC** — newline JSON header + raw bytes; AF_UNIX on the Pi, loopback TCP on
  the Windows dev box. The socket thread only enqueues; the loop thread executes,
  so the model is never touched from two threads.

Failure discipline is `read_coffee_level()`'s: the photo always goes out.

## 2. Benchmark (gym, Pi-anchored virtual time, real frames, real inference)

From `gym/BENCH.md` (typical day = 2026-09-01's 17 requests; burst = 09-03's 98):

| | legacy | streamlined |
|---|---|---|
| photo latency p50, typical / burst | 16.0 / 13.6 s | **3.0 / 3.0 s** |
| photo latency p90, stress (542 req) | 149 s | **6.2 s** |
| photo latency max, stress | 500 s | 26 s |
| requests answered from a ≤15 s-old sampler frame | – | 16/17 · 94/97 · 520/542 |
| sampler cadence | 33 s | 10 s (or as configured) |
| sampler blind hours per day (legacy rule) | 0.8–6.8 h | 0 |
| /graph renders per 90 calls | 90 | 36 |
| TTA=8 → TTA=1 change in the served reading | – | median 2 ml, p90 15–47 ml |
| Pi CPU-s/day, 10 s interval | 7.7 k | 10.3 k |
| Pi CPU-s/day, 30 s interval, same latency | – | **3.6 k** |

Latencies include an assumed 3 s Telegram upload in both designs. The
streamlined latency is the upload plus, when no fresh frame exists, one capture.

## 2b. Why the gate changed signal (gym/GATE2_*.md, GATE3_*.md, BENCH_MODELS*.md)

Measured against human clicks, blind archive set (99 records, Jan–Jun camera) and
the field set (31 pots, 2026-09 camera, survey clicks):

| what the 0.55 entropy gate does, v8 | kept | rejected |
|---|---|---|
| blind archive, median error | 24 records at 26.7 ml | 75 at 23.5 ml |
| field, median error | 8 pots at 51.4 ml | 23 at 29.2 ml |
| field non-empty, median error | 2 pots at 222 ml | 14 at 45.7 ml |

Entropy orders nothing; the coverage it costs buys no accuracy. Training the
entropy down (v9 fine-tune, sharpness 0.5, lr 3e-4) collapsed it to 0.13–0.18
so every pot passes, but repeatability went 11 → 92 ml and field non-empty error
50 → 89 ml: a sharper distribution is not a better one.

Temporal agreement, ordering the same blind records by disagreement with the
neighbouring archive frame (5 min apart, so a harsher test than the sampler's
10 s):

| blind archive, non-empty (n=57), v8 | 20 % coverage | 40 % | 60 % | 100 % |
|---|---|---|---|---|
| by entropy: median error | 41.9 ml | 25.5 | 24.2 | 34.4 |
| by neighbour disagreement: median error | **16.1 ml** | **14.2** | **21.3** | 34.4 |
| by neighbour disagreement: within 40 ml | 73 % | 74 % | 71 % | 56 % |

Hence `mode=agree`. The thresholds 40 / 90 ml are a starting point; the
records now carry `a`, so they can be fitted on a month of field data.

Accuracy itself is at the single-click label floor (README §8.3): v8-recipe
seeds differ by ±5 ml on the blind set, and on filled field carafes every
checkpoint sits at 45–50 ml median (n=16). New labels, not new models, move it.

## 3. Deployment

Live on kahviraspi since 2026-09-15.

1. On the Pi, from a checkout of this repo: `bash reader/install_reader.sh`. It
   builds a virtualenv beside the code, writes the unit with this checkout's
   paths, stops `kahvisampler` and starts `kahvi-reader`. The reader runs from
   the checkout; only data (readings, `latest.json`) lives outside it.
2. In the bot's `config.py`: `reader_service_socket = "/run/kahvi-sampler/ipc.sock"`,
   and point `coffee_reader_log` at the same data directory. Restart kahvibot.
   Without that line the bot behaves exactly as before.
3. Plug power arrives over MQTT; the installer copies the broker password to a
   file the service user can read. With no broker the filter still runs, it just
   has to infer brewing instead of being told.
4. Rollback: `systemctl disable --now kahvi-reader`, drop the config line.

Fix first, independent of all of the above: the power supply (ANALYSIS.md §3).

## 4. What is deliberately unchanged

fswebcam arguments (`-S 20`, 1280×720), the model, the crop chain, the JSONL
location and monthly rotation, the survey's frame cache, and the bot's own
fallback path.
