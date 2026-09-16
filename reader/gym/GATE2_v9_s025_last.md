# Gate v2 — learned reliability score vs entropy gate

Model dir: _work/onnx_v9_s025_last. 'Good' = |Δh|·1250 ≤ 40 ml vs the human click. Logistic regression on e, h, d, u, v, luma, is_left, fitted on 158 archive-era train records; evaluated on 99 blind archive records and 31 field pots.

Standardised weights: `{"e": -0.033, "h": 0.113, "d": 0.003, "u": 0.163, "v": -0.316, "luma": 0.165, "is_left": 0.193}`

## blind archive (Jan–Jun 2026 camera) (n=99)

Deployed gate e ≤ 0.55 keeps 99/99: kept median err 39.0 ml, rejected median err - ml. All readings: median 39.0 ml, 53% within 40 ml.

| coverage | entropy gate: median err / ≤40 ml | surface logit: median err / ≤40 ml | learned: median err / ≤40 ml |
|---|---|---|---|
| 20% | 46.9 / 40% | 34.4 / 60% | 41.2 / 50% |
| 30% | 41.2 / 50% | 37.7 / 50% | 42.9 / 47% |
| 40% | 38.6 / 52% | 35.0 / 52% | 41.2 / 50% |
| 50% | 36.3 / 54% | 38.2 / 52% | 42.9 / 48% |
| 60% | 33.7 / 59% | 39.0 / 51% | 39.0 / 53% |
| 70% | 33.8 / 58% | 46.3 / 48% | 39.0 / 54% |
| 80% | 33.7 / 58% | 40.3 / 49% | 39.0 / 53% |
| 90% | 34.5 / 55% | 39.8 / 52% | 39.0 / 53% |
| 100% | 39.0 / 53% | 39.0 / 53% | 39.0 / 53% |

## blind archive, non-empty only (human h ≥ 0.1) (n=71)

Deployed gate e ≤ 0.55 keeps 71/71: kept median err 48.0 ml, rejected median err - ml. All readings: median 48.0 ml, 44% within 40 ml.

| coverage | entropy gate: median err / ≤40 ml | surface logit: median err / ≤40 ml | learned: median err / ≤40 ml |
|---|---|---|---|
| 20% | 57.5 / 29% | 35.0 / 57% | 76.3 / 14% |
| 30% | 55.6 / 33% | 34.8 / 57% | 70.9 / 24% |
| 40% | 51.8 / 39% | 37.7 / 50% | 58.3 / 32% |
| 50% | 47.7 / 44% | 44.0 / 47% | 51.8 / 42% |
| 60% | 47.4 / 47% | 47.8 / 47% | 47.4 / 47% |
| 70% | 43.3 / 48% | 44.0 / 48% | 49.3 / 44% |
| 80% | 40.3 / 49% | 47.8 / 46% | 47.4 / 46% |
| 90% | 47.6 / 45% | 48.9 / 44% | 47.6 / 45% |
| 100% | 48.0 / 44% | 48.0 / 44% | 48.0 / 44% |

## field (2026-09 camera, survey clicks) (n=31)

Deployed gate e ≤ 0.55 keeps 31/31: kept median err 44.4 ml, rejected median err - ml. All readings: median 44.4 ml, 45% within 40 ml.

| coverage | entropy gate: median err / ≤40 ml | surface logit: median err / ≤40 ml | learned: median err / ≤40 ml |
|---|---|---|---|
| 20% | 17.7 / 67% | 75.7 / 33% | 33.1 / 50% |
| 30% | 14.4 / 67% | 49.7 / 33% | 17.2 / 67% |
| 40% | 17.7 / 58% | 64.3 / 33% | 19.1 / 58% |
| 50% | 32.7 / 50% | 45.8 / 44% | 44.9 / 44% |
| 60% | 42.0 / 47% | 78.9 / 37% | 44.4 / 47% |
| 70% | 31.5 / 50% | 51.0 / 41% | 43.2 / 45% |
| 80% | 42.0 / 48% | 49.7 / 40% | 42.0 / 48% |
| 90% | 43.2 / 46% | 47.5 / 43% | 43.2 / 46% |
| 100% | 44.4 / 45% | 44.4 / 45% | 44.4 / 45% |

## field, non-empty only (human h ≥ 0.1) (n=16)

Deployed gate e ≤ 0.55 keeps 16/16: kept median err 111.6 ml, rejected median err - ml. All readings: median 111.6 ml, 12% within 40 ml.

| coverage | entropy gate: median err / ≤40 ml | surface logit: median err / ≤40 ml | learned: median err / ≤40 ml |
|---|---|---|---|
| 20% | 196.0 / 0% | 49.7 / 33% | 78.9 / 33% |
| 30% | 124.0 / 0% | 49.7 / 40% | 78.9 / 20% |
| 40% | 122.7 / 17% | 75.7 / 33% | 100.2 / 17% |
| 50% | 110.2 / 12% | 64.3 / 25% | 111.6 / 12% |
| 60% | 110.2 / 10% | 88.9 / 20% | 111.6 / 10% |
| 70% | 98.9 / 18% | 98.9 / 18% | 121.5 / 9% |
| 80% | 101.8 / 15% | 101.8 / 15% | 121.5 / 8% |
| 90% | 111.6 / 14% | 112.9 / 14% | 111.6 / 7% |
| 100% | 111.6 / 12% | 111.6 / 12% | 111.6 / 12% |

