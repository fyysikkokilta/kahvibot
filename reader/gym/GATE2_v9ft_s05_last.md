# Gate v2 — learned reliability score vs entropy gate

Model dir: _work/onnx_v9ft_s05_last. 'Good' = |Δh|·1250 ≤ 40 ml vs the human click. Logistic regression on e, h, d, u, v, luma, is_left, fitted on 158 archive-era train records; evaluated on 99 blind archive records and 31 field pots.

Standardised weights: `{"e": -0.195, "h": 0.099, "d": 0.012, "u": 0.1, "v": -0.105, "luma": -0.026, "is_left": 0.2}`

## blind archive (Jan–Jun 2026 camera) (n=99)

Deployed gate e ≤ 0.55 keeps 98/99: kept median err 37.6 ml, rejected median err 11.0 ml. All readings: median 37.5 ml, 55% within 40 ml.

| coverage | entropy gate: median err / ≤40 ml | surface logit: median err / ≤40 ml | learned: median err / ≤40 ml |
|---|---|---|---|
| 20% | 41.0 / 50% | 50.1 / 40% | 41.0 / 50% |
| 30% | 30.0 / 57% | 48.5 / 43% | 38.6 / 53% |
| 40% | 26.9 / 60% | 49.0 / 42% | 30.3 / 57% |
| 50% | 27.7 / 64% | 48.2 / 44% | 27.7 / 60% |
| 60% | 30.2 / 58% | 44.0 / 46% | 29.0 / 59% |
| 70% | 33.6 / 57% | 39.8 / 51% | 29.0 / 58% |
| 80% | 33.6 / 56% | 39.8 / 51% | 33.6 / 56% |
| 90% | 34.4 / 55% | 39.8 / 51% | 33.6 / 56% |
| 100% | 37.5 / 55% | 37.5 / 55% | 37.5 / 55% |

## blind archive, non-empty only (human h ≥ 0.1) (n=71)

Deployed gate e ≤ 0.55 keeps 70/71: kept median err 45.0 ml, rejected median err 11.0 ml. All readings: median 44.0 ml, 46% within 40 ml.

| coverage | entropy gate: median err / ≤40 ml | surface logit: median err / ≤40 ml | learned: median err / ≤40 ml |
|---|---|---|---|
| 20% | 59.8 / 43% | 52.5 / 29% | 75.6 / 29% |
| 30% | 49.3 / 48% | 50.8 / 38% | 74.8 / 33% |
| 40% | 39.8 / 50% | 48.5 / 43% | 50.1 / 43% |
| 50% | 38.8 / 50% | 48.2 / 44% | 36.0 / 50% |
| 60% | 44.0 / 47% | 43.8 / 47% | 43.8 / 49% |
| 70% | 45.0 / 44% | 45.8 / 46% | 42.3 / 48% |
| 80% | 45.9 / 44% | 44.0 / 46% | 44.0 / 46% |
| 90% | 46.8 / 44% | 46.8 / 44% | 43.9 / 47% |
| 100% | 44.0 / 46% | 44.0 / 46% | 44.0 / 46% |

## field (2026-09 camera, survey clicks) (n=31)

Deployed gate e ≤ 0.55 keeps 31/31: kept median err 23.9 ml, rejected median err - ml. All readings: median 23.9 ml, 52% within 40 ml.

| coverage | entropy gate: median err / ≤40 ml | surface logit: median err / ≤40 ml | learned: median err / ≤40 ml |
|---|---|---|---|
| 20% | 40.1 / 50% | 102.5 / 33% | 51.6 / 33% |
| 30% | 61.8 / 44% | 57.8 / 33% | 41.4 / 44% |
| 40% | 51.6 / 42% | 59.8 / 33% | 30.7 / 50% |
| 50% | 32.7 / 50% | 59.8 / 38% | 17.2 / 56% |
| 60% | 41.4 / 47% | 42.1 / 47% | 18.5 / 63% |
| 70% | 32.7 / 50% | 49.9 / 45% | 19.2 / 59% |
| 80% | 41.4 / 48% | 42.1 / 48% | 20.0 / 56% |
| 90% | 32.7 / 50% | 33.0 / 50% | 23.4 / 54% |
| 100% | 23.9 / 52% | 23.9 / 52% | 23.9 / 52% |

## field, non-empty only (human h ≥ 0.1) (n=16)

Deployed gate e ≤ 0.55 keeps 16/16: kept median err 89.1 ml, rejected median err - ml. All readings: median 89.1 ml, 19% within 40 ml.

| coverage | entropy gate: median err / ≤40 ml | surface logit: median err / ≤40 ml | learned: median err / ≤40 ml |
|---|---|---|---|
| 20% | 108.4 / 0% | 18.5 / 67% | 268.3 / 0% |
| 30% | 61.8 / 40% | 147.3 / 40% | 147.3 / 0% |
| 40% | 65.8 / 33% | 102.5 / 33% | 127.8 / 0% |
| 50% | 68.0 / 25% | 59.8 / 25% | 89.1 / 25% |
| 60% | 89.1 / 20% | 59.8 / 30% | 65.8 / 20% |
| 70% | 69.9 / 18% | 61.8 / 27% | 61.8 / 27% |
| 80% | 108.4 / 15% | 66.2 / 23% | 66.2 / 23% |
| 90% | 115.8 / 14% | 68.0 / 21% | 68.0 / 21% |
| 100% | 89.1 / 19% | 89.1 / 19% | 89.1 / 19% |

