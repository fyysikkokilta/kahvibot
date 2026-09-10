# Gate v2 — learned reliability score vs entropy gate

Model dir: _work/onnx_v9ft_lr1e4_s025_last. 'Good' = |Δh|·1250 ≤ 40 ml vs the human click. Logistic regression on e, h, d, u, v, luma, is_left, fitted on 158 archive-era train records; evaluated on 99 blind archive records and 31 field pots.

Standardised weights: `{"e": -0.245, "h": -0.109, "d": -0.304, "u": -0.072, "v": 0.108, "luma": 0.229, "is_left": -0.015}`

## blind archive (Jan–Jun 2026 camera) (n=99)

Deployed gate e ≤ 0.55 keeps 96/99: kept median err 34.4 ml, rejected median err 99.3 ml. All readings: median 34.6 ml, 59% within 40 ml.

| coverage | entropy gate: median err / ≤40 ml | surface logit: median err / ≤40 ml | learned: median err / ≤40 ml |
|---|---|---|---|
| 20% | 33.7 / 60% | 45.9 / 45% | 38.4 / 60% |
| 30% | 20.6 / 73% | 44.6 / 47% | 38.9 / 57% |
| 40% | 23.6 / 75% | 40.4 / 50% | 36.9 / 60% |
| 50% | 29.0 / 74% | 40.4 / 50% | 30.5 / 64% |
| 60% | 30.6 / 69% | 39.6 / 53% | 30.6 / 68% |
| 70% | 30.2 / 70% | 39.6 / 52% | 30.2 / 70% |
| 80% | 30.9 / 66% | 37.2 / 54% | 32.6 / 63% |
| 90% | 33.7 / 62% | 36.7 / 56% | 34.3 / 61% |
| 100% | 34.6 / 59% | 34.6 / 59% | 34.6 / 59% |

## blind archive, non-empty only (human h ≥ 0.1) (n=71)

Deployed gate e ≤ 0.55 keeps 69/71: kept median err 41.2 ml, rejected median err 469.3 ml. All readings: median 41.2 ml, 49% within 40 ml.

| coverage | entropy gate: median err / ≤40 ml | surface logit: median err / ≤40 ml | learned: median err / ≤40 ml |
|---|---|---|---|
| 20% | 48.0 / 43% | 45.9 / 43% | 45.5 / 50% |
| 30% | 28.7 / 62% | 50.6 / 43% | 39.6 / 52% |
| 40% | 33.9 / 61% | 44.6 / 46% | 40.4 / 50% |
| 50% | 31.9 / 64% | 40.4 / 50% | 33.9 / 58% |
| 60% | 33.7 / 60% | 39.6 / 51% | 31.2 / 63% |
| 70% | 35.1 / 58% | 38.2 / 52% | 31.0 / 62% |
| 80% | 36.7 / 54% | 39.6 / 51% | 36.5 / 56% |
| 90% | 38.4 / 52% | 40.4 / 50% | 36.9 / 53% |
| 100% | 41.2 / 49% | 41.2 / 49% | 41.2 / 49% |

## field (2026-09 camera, survey clicks) (n=31)

Deployed gate e ≤ 0.55 keeps 31/31: kept median err 34.1 ml, rejected median err - ml. All readings: median 34.1 ml, 55% within 40 ml.

| coverage | entropy gate: median err / ≤40 ml | surface logit: median err / ≤40 ml | learned: median err / ≤40 ml |
|---|---|---|---|
| 20% | 48.9 / 33% | 37.2 / 50% | 43.1 / 33% |
| 30% | 42.4 / 44% | 43.8 / 44% | 42.4 / 44% |
| 40% | 43.1 / 42% | 44.6 / 42% | 38.2 / 50% |
| 50% | 38.2 / 50% | 43.1 / 44% | 31.5 / 56% |
| 60% | 42.4 / 47% | 43.8 / 42% | 34.1 / 53% |
| 70% | 38.2 / 50% | 35.7 / 50% | 31.5 / 55% |
| 80% | 29.0 / 56% | 38.2 / 52% | 29.0 / 56% |
| 90% | 31.5 / 57% | 33.6 / 54% | 31.5 / 57% |
| 100% | 34.1 / 55% | 34.1 / 55% | 34.1 / 55% |

## field, non-empty only (human h ≥ 0.1) (n=16)

Deployed gate e ≤ 0.55 keeps 16/16: kept median err 54.2 ml, rejected median err - ml. All readings: median 54.2 ml, 25% within 40 ml.

| coverage | entropy gate: median err / ≤40 ml | surface logit: median err / ≤40 ml | learned: median err / ≤40 ml |
|---|---|---|---|
| 20% | 43.8 / 0% | 29.0 / 67% | 43.8 / 0% |
| 30% | 43.8 / 20% | 29.0 / 60% | 43.8 / 20% |
| 40% | 54.1 / 17% | 37.2 / 50% | 49.0 / 17% |
| 50% | 54.1 / 25% | 44.6 / 38% | 49.0 / 25% |
| 60% | 59.3 / 20% | 44.6 / 40% | 59.4 / 20% |
| 70% | 54.3 / 18% | 45.5 / 36% | 54.3 / 27% |
| 80% | 54.3 / 23% | 45.5 / 31% | 54.3 / 23% |
| 90% | 59.4 / 21% | 49.8 / 29% | 54.2 / 21% |
| 100% | 54.2 / 25% | 54.2 / 25% | 54.2 / 25% |

