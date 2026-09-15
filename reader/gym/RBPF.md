# Row-distribution filter vs point estimate + gate

Model `onnx_v8_logits`. Blind set: 99 frozen hand-clicked pot-views (71 non-empty). Error is |estimate - click| in ml; a single click carries ~21 ml of noise, so differences under ~10 ml are not differences.

## 1. Accuracy: soft-argmax vs posterior mean

| set | soft-argmax (deployed) | posterior mode | posterior median | posterior mean |
|---|---|---|---|---|
| all (n=99) | 29.9 | 33.7 | 71.7 | 88.6 |
| non-empty (n=71) | 29.9 | 33.7 | 36.1 | 38.2 |

The mean is included to show why it must not be the published number: the robust mixture's uniform pedestal pulls it toward mid-scale, and on a bimodal frame it lands between the two candidate surfaces. The mode is the like-for-like comparison with a soft-argmax.

### 1b. Mode decomposition, which is what should actually be published

Summarising each mode of the calibrated density by a soft-argmax *within its own
basin* - the statistic v8 was trained to produce - rather than by a global
argmax over a density that includes the robust pedestal:

| blind set | deployed point estimate | heaviest mode | best available mode (oracle) |
|---|---|---|---|
| all (n=99) | 29.9 | 29.2 | 27.9 |
| the 16 bimodal frames | 30.9 | 25.9 | 17.5 |

Two things follow. Nothing is lost on ordinary frames: the heaviest mode equals
the deployed estimate to within click noise. And on bimodal frames the correct
surface is *present among the modes* - an oracle choosing between them would
reach 17.5 ml - so the remaining error there is a selection problem, which is
exactly what the filter's dynamics and the plug are for.

## 2. Reliability: does the posterior's own spread order errors?

Keeping only the best-scoring fraction of readings. Entropy was the deployed gate's signal; posterior sd is what replaces it.

### all (n=99)

| kept | by entropy: median err / within 40 ml | by posterior sd: median err / within 40 ml |
|---|---|---|
| 20% | 33.7 / 55% | 22.2 / 80% |
| 40% | 35.3 / 55% | 24.2 / 70% |
| 60% | 33.7 / 61% | 26.7 / 63% |
| 80% | 36.9 / 57% | 30.5 / 58% |
| 100% | 33.7 / 59% | 33.7 / 59% |

### non-empty (n=71)

| kept | by entropy: median err / within 40 ml | by posterior sd: median err / within 40 ml |
|---|---|---|
| 20% | 52.5 / 29% | 23.3 / 79% |
| 40% | 37.3 / 57% | 24.2 / 75% |
| 60% | 33.7 / 58% | 24.5 / 67% |
| 80% | 36.6 / 56% | 26.7 / 63% |
| 100% | 33.7 / 56% | 33.7 / 56% |

## 3. Dynamics: impossible rises over a replayed day

Only a brew can raise the level. Every other rise is the reader flipping between surfaces. No plug data exists for the archive, so the filter has to infer brewing here - the hardest case for it.

| day | pot | steps | raw rises >40 ml | filtered rises | raw falls | filtered falls | raw jitter | filtered jitter |
|---|---|---|---|---|---|---|---|---|
| 2026-01-30 | left | 235 | 4 | 1 | 4 | 4 | 0 ml | 5 ml |
| 2026-01-30 | right | 221 | 3 | 2 | 6 | 5 | 21 ml | 15 ml |
| 2026-01-31 | left | 237 | 0 | 0 | 0 | 6 | 0 ml | 15 ml |
| 2026-01-31 | right | 9 | 0 | 1 | 0 | 4 | 28 ml | 6 ml |

Total rises over 40 ml: **7 raw -> 4 filtered**.

Read this cautiously. The archive is one frame per ~5 minutes with no plug data,
so brewing has to be inferred and a five-minute gap genuinely permits a pour;
there are only 7 raw violations across four pot-days, which is too few to
separate a real improvement from noise. The regime this filter was designed for
is the deployed one: 10 s frames with the plug pinning the element, where the
field log showed 786 impossible rises. That test needs a fortnight of live data
and is the first thing to run once the reader service and the plugs are both up.

One real cost is visible here: where the raw reader sits exactly flat on an empty
pot, the filter shows 5-15 ml of jitter, which is its own process noise
(`Physics.volume_walk_ml_s`). It should be lowered, or made conditional on the
pot being non-empty, before deployment.

## 4. What this means for the gate

The gate accepted or rejected a frame on entropy and published nothing when it rejected, which cost ~70 % of readings. The filter publishes every tick with an interval attached: a diffuse frame widens the posterior instead of deleting it, and a bimodal frame keeps both surfaces alive until the dynamics or the plug choose. Coverage becomes 100 % by construction; the honest quantity to show a user is the interval, not a pass/fail flag.

