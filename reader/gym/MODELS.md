# Next-generation reader: what was trained, what the gym says, what to deploy

Session 2026-09-09 22:50 → 2026-09-10 09:45, one laptop CPU (i7-12700H), with one
battery-induced shutdown at ~03:15. Nine checkpoints scored, five of them trained tonight. Detailed tables: `BENCH_MODELS.md` (all
candidates), `BENCH_MODELS_<tag>.md` (per candidate), `GATE2_<tag>.md`,
`GATE3_<tag>.md`, `BENCH.md` (pipeline). Method: `README.md` in this folder.

## 1. The question the field data posed

The Pi logs (kahviraspi_logs_2026-09-09/ANALYSIS.md) showed the deployed reader
abstaining on 70–75 % of pots and on nearly every filled carafe, because the
abstention gate is `surface_entropy ≤ 0.55` and entropy rises with fill level.
Accuracy, meanwhile, is at the single-click label floor (coffee10/README.md §8.3).
So the candidates were aimed at the gate, not at accuracy: teach the reader a
sharper surface distribution where a human could see the surface
(`train.py --w-sharp`, on the 158 hand-clicked training records), fine-tuned from
v8 and from scratch.

## 2. Candidates and results

Blind = 99 frozen hand-clicked records, Jan–Jun 2026 camera. Field = 31 pots on
the 2026-09 camera with survey clicks (16 non-empty). Errors are medians in ml
against the click; a single click carries ~21 ml of noise, so differences under
~10 ml on these sample sizes are not differences. Repeatability = the trainer's
own metric on validation pairs (`repeat_ml_robust_sd`, v8 = 25 ml).

| candidate | recipe | blind fill | blind non-empty | field all | field non-empty | repeatability | field coverage at e≤0.55 |
|---|---|---|---|---|---|---|---|
| **v8** (deployed) | v8 recipe, 3000 steps | 30.9 | 28.8 | 44.5 | 49.8 | 25 | 29 % |
| v18 | v8 recipe, seed 1 | 25.5 | 34.8 | 53.0 | 86.1 | – | 28 % |
| v20 last | v8 + unlabelled invariance | 24.6 | 42.0 | 22.3 | 48.0 | – | 15 % |
| v43 last | v8, pair-frac 0.5 | 27.2 | 31.8 | 49.2 | 45.3 | – | 20 % |
| v9ft s0.5 | fine-tune v8, lr 3e-4, sharp 0.5 | 43.9 | 39.7 | 23.9 | 89.1 | 92 | 96 % |
| v9ft s0.25 | fine-tune v8, lr 1e-4, sharp 0.25 | 32.4 | 35.5 | 34.1 | 54.2 | 67 | 95 % |
| v9ft s0.10 | fine-tune v8, lr 1e-4, sharp 0.10 | 29.7 | 37.3 | 31.0 | 41.6 | 64 | 87 % |
| v9 scratch s0.25 | v8 recipe + sharp 0.25, 3000 steps | 62.7 | 46.4 | 44.4 | 111.6 | 99 | 96 % |
| v9ft s0 (control) | fine-tune v8, lr 1e-4, no sharpness | 30.8 | 30.7 | 35.3 | 43.7 | 51 | 28 % |

Reading it:

* **Sharpness training does what it says and nothing useful.** Entropy collapses
  (median 0.04–0.46 against v8's 0.57), so every pot passes any threshold, but
  the gate was never carrying information (§3), so this only removes a
  filter that was random. Meanwhile repeatability degrades 2.5–4× and, from
  scratch, accuracy halves. The gentler fine-tunes stay within click noise of v8
  on accuracy while losing repeatability.
* **The control isolates the two effects.** Fine-tuning v8 for 1200 steps with no
  sharpness term leaves accuracy and entropy where v8 had them (28 % coverage at
  0.55, 31 ml blind) but still doubles the repeatability metric (25 → 51 ml): the
  OneCycle restart itself unsettles the reader. Sharpness then adds the rest
  (64–99 ml) and, from scratch, the accuracy loss. Neither is worth deploying.
* **The v8-recipe seeds (v8, v18, v20, v43) differ by ±5 ml on the blind set and
  by ±30 ml on 16 field pots.** That is the noise floor, not a ranking. v20's
  apparent field advantage is on empties.
* **On filled carafes in the field every model sits at 45–50 ml median.** Nothing
  trained tonight moves that; the project README's diagnosis stands: repeat
  clicks and a geometric base, not architecture, are the path below 25 ml.

## 3. Gates: entropy carries no signal; temporal agreement does

Ordering readings by each signal and keeping the best fraction (GATE2/GATE3, v8):

| blind non-empty clicks (n=57), median error of the kept readings | 20 % kept | 40 % | 60 % | all |
|---|---|---|---|---|
| by entropy (deployed signal) | 41.9 ml | 25.5 | 24.2 | 34.4 |
| by disagreement with the neighbouring frame | **16.1 ml** | **14.2** | **21.3** | 34.4 |

On the field set the 0.55 entropy gate keeps 8 of 31 pots at 51 ml median while
rejecting 23 at 29 ml; on non-empty pots it keeps 2 at 222 ml. A learned
logistic gate over (e, h, d, usable/surface logits, luma, side) adds a few
points on the archive and nothing reliable on 31 field pots.

Consequence, implemented in `pipeline/gate.py` and `pipeline/service.py`: every
record now carries `a`, the millilitres of disagreement with the previous
reading of the same pot (the streamlined sampler provides a neighbour every
~10 s). Default gate: `ok` if `a ≤ 40 ml`, `uncertain` if `a ≤ 90 ml`, else
abstain; entropy decides only when no recent neighbour exists. Thresholds are a
starting point to be fitted on a month of field records.

## 4. Recommendation

1. Deploy the **streamlined pipeline with v8 unchanged** (`PIPELINE.md`): photo
   latency 16 → 3 s, bursts absorbed, 10 s readings, and the agreement gate.
2. Do not deploy any v9 candidate. Keep `--w-sharp` in the trainer as a
   documented negative result.
3. Fit the agreement thresholds and re-check the field error tables after two
   weeks of `a`-bearing records; the gym (`models.py`, `gate2.py`) reruns in
   minutes with blind evaluations cached.
4. For accuracy, follow README §9: cup graduations, vessel geometry, repeat clicks.

## 5. Machine notes

The laptop's adapter cannot supply 20 threads of load; it discharged and shut
down once at ~03:15. `gym/power_governor.py` now suspends the heavy jobs below
40 % battery and resumes above 75 %; training runs use 8 threads. Memory: the
crop cache memmap plus torch is ~3.4 GB; running a torch evaluation alongside
training tipped the 17 GB host into the harness's memory guard, so the finish
chain scores each checkpoint only between runs.
