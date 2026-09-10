# Gate v2 — learned reliability score vs entropy gate

Model dir: _work/onnx_v9_s025_best. 'Good' = |Δh|·1250 ≤ 40 ml vs the human click. Logistic regression on e, h, d, u, v, luma, is_left, fitted on 158 archive-era train records; evaluated on 99 blind archive records and 31 field pots.

Standardised weights: `{"e": -0.185, "h": -0.153, "d": 0.028, "u": 0.155, "v": 0.172, "luma": 0.126, "is_left": 0.226}`

## blind archive (Jan–Jun 2026 camera) (n=99)

Deployed gate e ≤ 0.55 keeps 99/99: kept median err 42.8 ml, rejected median err - ml. All readings: median 42.8 ml, 47% within 40 ml.

| coverage | entropy gate: median err / ≤40 ml | surface logit: median err / ≤40 ml | learned: median err / ≤40 ml |
|---|---|---|---|
| 20% | 39.6 / 50% | 47.3 / 40% | 44.5 / 45% |
| 30% | 40.9 / 47% | 44.5 / 47% | 36.6 / 53% |
| 40% | 40.9 / 48% | 44.5 / 45% | 39.2 / 50% |
| 50% | 42.0 / 46% | 45.7 / 44% | 38.8 / 52% |
| 60% | 41.2 / 47% | 48.9 / 42% | 38.2 / 53% |
| 70% | 42.8 / 46% | 45.8 / 43% | 39.8 / 51% |
| 80% | 42.8 / 47% | 43.3 / 47% | 40.6 / 49% |
| 90% | 43.3 / 45% | 41.2 / 48% | 41.2 / 48% |
| 100% | 42.8 / 47% | 42.8 / 47% | 42.8 / 47% |

## blind archive, non-empty only (human h ≥ 0.1) (n=71)

Deployed gate e ≤ 0.55 keeps 71/71: kept median err 43.3 ml, rejected median err - ml. All readings: median 43.3 ml, 45% within 40 ml.

| coverage | entropy gate: median err / ≤40 ml | surface logit: median err / ≤40 ml | learned: median err / ≤40 ml |
|---|---|---|---|
| 20% | 36.8 / 50% | 44.5 / 43% | 47.3 / 43% |
| 30% | 38.7 / 52% | 45.6 / 43% | 45.8 / 43% |
| 40% | 39.6 / 50% | 44.5 / 46% | 43.1 / 43% |
| 50% | 38.1 / 53% | 44.5 / 44% | 43.1 / 44% |
| 60% | 40.6 / 49% | 43.3 / 47% | 40.6 / 49% |
| 70% | 40.9 / 48% | 45.7 / 44% | 44.1 / 44% |
| 80% | 41.2 / 47% | 45.8 / 44% | 41.2 / 47% |
| 90% | 42.0 / 47% | 45.3 / 45% | 42.0 / 47% |
| 100% | 43.3 / 45% | 43.3 / 45% | 43.3 / 45% |

## field (2026-09 camera, survey clicks) (n=31)

Deployed gate e ≤ 0.55 keeps 31/31: kept median err 63.5 ml, rejected median err - ml. All readings: median 63.5 ml, 29% within 40 ml.

| coverage | entropy gate: median err / ≤40 ml | surface logit: median err / ≤40 ml | learned: median err / ≤40 ml |
|---|---|---|---|
| 20% | 89.1 / 17% | 74.3 / 17% | 70.5 / 33% |
| 30% | 84.5 / 22% | 64.0 / 22% | 93.1 / 22% |
| 40% | 63.8 / 25% | 72.4 / 25% | 87.0 / 25% |
| 50% | 63.8 / 25% | 63.8 / 19% | 58.1 / 31% |
| 60% | 80.7 / 21% | 64.0 / 21% | 64.0 / 32% |
| 70% | 63.8 / 27% | 63.8 / 23% | 72.4 / 27% |
| 80% | 64.0 / 24% | 63.5 / 28% | 54.6 / 32% |
| 90% | 63.8 / 29% | 63.8 / 29% | 59.3 / 29% |
| 100% | 63.5 / 29% | 63.5 / 29% | 63.5 / 29% |

## field, non-empty only (human h ≥ 0.1) (n=16)

Deployed gate e ≤ 0.55 keeps 16/16: kept median err 72.4 ml, rejected median err - ml. All readings: median 72.4 ml, 19% within 40 ml.

| coverage | entropy gate: median err / ≤40 ml | surface logit: median err / ≤40 ml | learned: median err / ≤40 ml |
|---|---|---|---|
| 20% | 84.5 / 0% | 93.6 / 0% | 143.7 / 0% |
| 30% | 84.5 / 20% | 64.0 / 20% | 93.6 / 0% |
| 40% | 74.3 / 17% | 74.3 / 17% | 118.7 / 0% |
| 50% | 63.8 / 25% | 74.3 / 12% | 87.2 / 12% |
| 60% | 59.1 / 30% | 74.3 / 20% | 82.7 / 10% |
| 70% | 63.5 / 27% | 80.8 / 18% | 84.5 / 9% |
| 80% | 63.5 / 23% | 64.0 / 15% | 84.5 / 15% |
| 90% | 63.8 / 21% | 72.4 / 14% | 82.7 / 14% |
| 100% | 72.4 / 19% | 72.4 / 19% | 72.4 / 19% |

