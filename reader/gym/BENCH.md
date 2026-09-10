# Pipeline benchmark — 2026-09-09T22:45

Machine: i7-12700H, 20 threads, onnxruntime CPU, 2 intra-op threads. Archive frames: 10099 (2026-01-12 .. 2026-06-13). Model: C:\Users\Käyttäjä\Documents\projects\lifestyle\coffee\coffee_mesh_pred\_work\onnx.

## 1. Microbenchmarks (this machine, median over 20 frames)

| stage | local s | Pi-projected s |
|---|---|---|
| cold_subprocess_tta8_s | 2.015 | - |
| warm_detect_s | 0.035 | 0.46 |
| warm_read_tta1_s | 0.099 | 1.28 |
| warm_read_tta8_s | 0.583 | 7.54 |
| warm_detect_plus_tta8_s | 0.619 | 8.00 |
| warm_detect_plus_tta1_s | 0.134 | 1.74 |

Pi scale factor = 12.9 local→Pi, anchored on the Pi's measured 8 s detect+TTA8 read. Cold-start on the Pi is an assumption (3 s); fswebcam 2 s.

## 2. Numerics

WarmReader + legacy_pots vs read_frame.FrameReader on 20 frames: **0 mismatches**.

## 3. Scenarios (virtual day 06:00–22:00, real frames, real inference)

### typical day (2026-09-01 pattern, 17 photos) on 2026-01-30

| metric | legacy | streamlined |
|---|---|---|
| requests | 17 | 17 |
| photo latency p50 (s) | 16.0 | 3.0 |
| photo latency p90 (s) | 18.9 | 6.3 |
| photo latency max (s) | 24.5 | 6.4 |
| reading latency p50 (s) | 16.0 | 0.0 |
| requests served from a fresh sampler frame | - | 16 |
| camera captures (bot + sampler) | 1315 | 4497 |
| sampler lit ticks | 1045 | 4242 |
| sampler cadence median (s) | 33.0 | 10.0 |
| sampler blind hours (legacy rule) | 2.0 | - |
| Pi CPU-seconds, whole day | 7698 | 10346 |
| records written | 1315 | 4496 |
| /graph calls | - | 2 |
| /graph renders (mtime key vs last-usable key) | 2 | 2 |

Sampler pot readings: legacy 2090 (usable at 0.55: 952) · streamlined 8484 (usable at new gate: 8378)

TTA=8 (legacy bot) vs TTA=1 (service) on the same frames, n=34: median |Δml| 2.3, p90 14.8, median |Δh| 0.0038

### burst day (2026-09-03 pattern, 98 photos) on 2026-01-31

| metric | legacy | streamlined |
|---|---|---|
| requests | 97 | 97 |
| photo latency p50 (s) | 13.6 | 3.0 |
| photo latency p90 (s) | 16.8 | 5.2 |
| photo latency max (s) | 19.5 | 6.2 |
| reading latency p50 (s) | 13.6 | 0.0 |
| requests served from a fresh sampler frame | - | 94 |
| camera captures (bot + sampler) | 1432 | 4310 |
| sampler lit ticks | 1046 | 4016 |
| sampler cadence median (s) | 33.0 | 10.0 |
| sampler blind hours (legacy rule) | 0.8 | - |
| Pi CPU-seconds, whole day | 8411 | 7803 |
| records written | 1432 | 4307 |
| /graph calls | - | 16 |
| /graph renders (mtime key vs last-usable key) | 16 | 4 |

Sampler pot readings: legacy 1277 (usable at 0.55: 747) · streamlined 4975 (usable at new gate: 4220)

TTA=8 (legacy bot) vs TTA=1 (service) on the same frames, n=97: median |Δml| 0.0, p90 46.9, median |Δh| 0.0093

### stress (synthetic): 1 req/min 09-17, 40 requests 5 s apart at 10:00, 20 requests 3 s apart at 11:30, on 2026-02-01

| metric | legacy | streamlined |
|---|---|---|
| requests | 542 | 542 |
| photo latency p50 (s) | 15.8 | 3.0 |
| photo latency p90 (s) | 149.4 | 6.2 |
| photo latency max (s) | 499.8 | 25.7 |
| reading latency p50 (s) | 15.8 | 0.0 |
| requests served from a fresh sampler frame | - | 520 |
| camera captures (bot + sampler) | 1707 | 3873 |
| sampler lit ticks | 800 | 3469 |
| sampler cadence median (s) | 33.0 | 10.0 |
| sampler blind hours (legacy rule) | 6.8 | - |
| Pi CPU-seconds, whole day | 12420 | 8779 |
| records written | 1707 | 3854 |
| /graph calls | - | 90 |
| /graph renders (mtime key vs last-usable key) | 90 | 36 |

Sampler pot readings: legacy 1558 (usable at 0.55: 391) · streamlined 6740 (usable at new gate: 6529)

TTA=8 (legacy bot) vs TTA=1 (service) on the same frames, n=1084: median |Δml| 2.1, p90 17.5, median |Δh| 0.0029

## 3b. Streamlined service: sampling interval trade-off (typical day)

| interval s | reuse age s | requests reused | photo p50 s | photo p90 s | lit ticks | cadence median s | Pi CPU-s/day | records |
|---|---|---|---|---|---|---|---|---|
| 10 | 15 | 16/17 | 3.0 | 6.3 | 4242 | 10.0 | 10346 | 4496 |
| 15 | 22 | 16/17 | 3.0 | 5.3 | 2828 | 15.0 | 7021 | 3082 |
| 20 | 30 | 16/17 | 3.0 | 5.0 | 2121 | 20.0 | 5276 | 2375 |
| 30 | 45 | 16/17 | 3.0 | 5.2 | 1414 | 30.0 | 3560 | 1668 |

## 4. Gate sweep on 591 pot readings from archive frames

| gate | coverage | n | of which ≥125 ml |
|---|---|---|---|
| 0.55 | 39% | 231 | 28 |
| 0.58 | 68% | 403 | 45 |
| 0.60 | 84% | 494 | 84 |
| 0.62 | 88% | 520 | 100 |
| 0.65 | 92% | 541 | 117 |
| 0.70 | 94% | 555 | 127 |

## 5. Cost model

Pi 3B cost model, anchored to what the Pi's own logs measured.

Measured on kahviraspi 2026-08-29..09-09 (kahviraspi_logs_2026-09-09/):
  * bot reader subprocess, read only (captured_at - read_at): median 8 s, max 10 s,
    TTA=8, fresh detect, no CPU quota
  * legacy sampler lit tick under CPUQuota=25%: 33 s cadence = 10 s interval + 23 s
    tick wall; TTA=8 probe ticks 106 s cadence; dark ticks exactly 60 s
  * fswebcam -S 20 at 1280x720: ~2 s (README; consistent with 13 s user latency
    = 2 s capture + ~8 s read + ~3 s cold start/upload)
Everything else here is an assumption and is labelled as such.

