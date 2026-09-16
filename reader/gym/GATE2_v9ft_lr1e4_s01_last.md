# Gate v2 — learned reliability score vs entropy gate

Model dir: _work/onnx_v9ft_lr1e4_s01_last. 'Good' = |Δh|·1250 ≤ 40 ml vs the human click. Logistic regression on e, h, d, u, v, luma, is_left, fitted on 158 archive-era train records; evaluated on 99 blind archive records and 31 field pots.

Standardised weights: `{"e": -0.1, "h": -0.456, "d": -0.1, "u": 0.05, "v": 0.049, "luma": 0.398, "is_left": 0.119}`

## blind archive (Jan–Jun 2026 camera) (n=99)

Deployed gate e ≤ 0.55 keeps 87/99: kept median err 27.0 ml, rejected median err 82.0 ml. All readings: median 29.1 ml, 64% within 40 ml.

| coverage | entropy gate: median err / ≤40 ml | surface logit: median err / ≤40 ml | learned: median err / ≤40 ml |
|---|---|---|---|
| 20% | 21.2 / 80% | 35.6 / 60% | 30.0 / 75% |
| 30% | 24.6 / 70% | 33.5 / 60% | 27.6 / 73% |
| 40% | 26.8 / 65% | 31.0 / 60% | 29.8 / 68% |
| 50% | 27.6 / 70% | 31.0 / 60% | 27.9 / 70% |
| 60% | 27.0 / 69% | 33.3 / 59% | 30.5 / 64% |
| 70% | 28.1 / 68% | 33.8 / 58% | 27.0 / 67% |
| 80% | 28.1 / 67% | 33.4 / 58% | 27.0 / 66% |
| 90% | 28.1 / 67% | 33.4 / 61% | 29.0 / 66% |
| 100% | 29.1 / 64% | 29.1 / 64% | 29.1 / 64% |

## blind archive, non-empty only (human h ≥ 0.1) (n=71)

Deployed gate e ≤ 0.55 keeps 62/71: kept median err 33.3 ml, rejected median err 82.9 ml. All readings: median 37.4 ml, 54% within 40 ml.

| coverage | entropy gate: median err / ≤40 ml | surface logit: median err / ≤40 ml | learned: median err / ≤40 ml |
|---|---|---|---|
| 20% | 32.5 / 50% | 35.6 / 64% | 51.4 / 36% |
| 30% | 37.4 / 52% | 37.4 / 57% | 46.6 / 43% |
| 40% | 40.8 / 50% | 33.5 / 61% | 41.3 / 50% |
| 50% | 33.5 / 56% | 31.0 / 61% | 41.0 / 50% |
| 60% | 37.4 / 53% | 28.7 / 60% | 38.5 / 51% |
| 70% | 33.6 / 58% | 31.0 / 60% | 31.2 / 56% |
| 80% | 33.8 / 56% | 33.3 / 58% | 33.8 / 54% |
| 90% | 33.3 / 58% | 35.6 / 53% | 37.9 / 53% |
| 100% | 37.4 / 54% | 37.4 / 54% | 37.4 / 54% |

## field (2026-09 camera, survey clicks) (n=31)

Deployed gate e ≤ 0.55 keeps 25/31: kept median err 39.1 ml, rejected median err 17.6 ml. All readings: median 31.0 ml, 58% within 40 ml.

| coverage | entropy gate: median err / ≤40 ml | surface logit: median err / ≤40 ml | learned: median err / ≤40 ml |
|---|---|---|---|
| 20% | 24.3 / 50% | 26.7 / 67% | 3.8 / 83% |
| 30% | 20.2 / 56% | 23.9 / 67% | 5.1 / 78% |
| 40% | 32.8 / 50% | 26.7 / 58% | 28.1 / 75% |
| 50% | 30.2 / 56% | 26.7 / 56% | 31.9 / 62% |
| 60% | 40.2 / 47% | 23.9 / 63% | 32.8 / 58% |
| 70% | 39.7 / 50% | 30.2 / 59% | 31.9 / 59% |
| 80% | 39.1 / 52% | 31.0 / 60% | 31.0 / 60% |
| 90% | 31.9 / 57% | 30.2 / 61% | 31.9 / 57% |
| 100% | 31.0 / 58% | 31.0 / 58% | 31.0 / 58% |

## field, non-empty only (human h ≥ 0.1) (n=16)

Deployed gate e ≤ 0.55 keeps 11/16: kept median err 46.8 ml, rejected median err 22.6 ml. All readings: median 41.6 ml, 44% within 40 ml.

| coverage | entropy gate: median err / ≤40 ml | surface logit: median err / ≤40 ml | learned: median err / ≤40 ml |
|---|---|---|---|
| 20% | 46.8 / 0% | 29.4 / 67% | 151.2 / 0% |
| 30% | 46.8 / 20% | 29.4 / 60% | 46.8 / 0% |
| 40% | 55.5 / 17% | 26.7 / 67% | 99.0 / 0% |
| 50% | 44.9 / 25% | 26.7 / 62% | 44.9 / 25% |
| 60% | 55.5 / 20% | 26.7 / 60% | 41.6 / 40% |
| 70% | 46.8 / 27% | 29.4 / 55% | 42.9 / 36% |
| 80% | 42.9 / 38% | 40.2 / 46% | 42.9 / 38% |
| 90% | 41.6 / 43% | 34.8 / 50% | 41.6 / 43% |
| 100% | 41.6 / 44% | 41.6 / 44% | 41.6 / 44% |

