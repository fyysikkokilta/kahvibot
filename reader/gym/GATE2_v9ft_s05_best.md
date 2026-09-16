# Gate v2 — learned reliability score vs entropy gate

Model dir: _work/onnx_v9ft_s05_best. 'Good' = |Δh|·1250 ≤ 40 ml vs the human click. Logistic regression on e, h, d, u, v, luma, is_left, fitted on 158 archive-era train records; evaluated on 99 blind archive records and 31 field pots.

Standardised weights: `{"e": 0.008, "h": -0.498, "d": -0.179, "u": -0.129, "v": 0.241, "luma": 0.135, "is_left": 0.027}`

## blind archive (Jan–Jun 2026 camera) (n=99)

Deployed gate e ≤ 0.55 keeps 97/99: kept median err 33.5 ml, rejected median err 231.6 ml. All readings: median 33.8 ml, 56% within 40 ml.

| coverage | entropy gate: median err / ≤40 ml | surface logit: median err / ≤40 ml | learned: median err / ≤40 ml |
|---|---|---|---|
| 20% | 34.1 / 55% | 43.4 / 40% | 34.7 / 60% |
| 30% | 20.5 / 67% | 56.7 / 33% | 33.2 / 60% |
| 40% | 27.0 / 65% | 55.6 / 35% | 32.9 / 62% |
| 50% | 29.1 / 66% | 47.3 / 44% | 32.3 / 64% |
| 60% | 29.1 / 63% | 42.5 / 46% | 32.5 / 61% |
| 70% | 30.3 / 61% | 40.2 / 49% | 31.6 / 65% |
| 80% | 31.6 / 61% | 40.2 / 49% | 32.0 / 63% |
| 90% | 33.2 / 60% | 36.8 / 53% | 33.3 / 58% |
| 100% | 33.8 / 56% | 33.8 / 56% | 33.8 / 56% |

## blind archive, non-empty only (human h ≥ 0.1) (n=71)

Deployed gate e ≤ 0.55 keeps 69/71: kept median err 40.2 ml, rejected median err 231.6 ml. All readings: median 40.3 ml, 48% within 40 ml.

| coverage | entropy gate: median err / ≤40 ml | surface logit: median err / ≤40 ml | learned: median err / ≤40 ml |
|---|---|---|---|
| 20% | 42.0 / 50% | 40.0 / 50% | 41.1 / 50% |
| 30% | 35.8 / 52% | 46.4 / 38% | 39.9 / 52% |
| 40% | 38.0 / 50% | 52.3 / 36% | 37.8 / 54% |
| 50% | 32.8 / 56% | 55.6 / 36% | 37.8 / 53% |
| 60% | 35.6 / 53% | 51.1 / 40% | 33.3 / 58% |
| 70% | 35.7 / 52% | 47.3 / 44% | 33.4 / 58% |
| 80% | 35.8 / 51% | 40.3 / 47% | 35.8 / 53% |
| 90% | 40.0 / 50% | 40.3 / 48% | 40.0 / 50% |
| 100% | 40.3 / 48% | 40.3 / 48% | 40.3 / 48% |

## field (2026-09 camera, survey clicks) (n=31)

Deployed gate e ≤ 0.55 keeps 31/31: kept median err 57.6 ml, rejected median err - ml. All readings: median 57.6 ml, 39% within 40 ml.

| coverage | entropy gate: median err / ≤40 ml | surface logit: median err / ≤40 ml | learned: median err / ≤40 ml |
|---|---|---|---|
| 20% | 79.8 / 0% | 79.3 / 33% | 23.8 / 83% |
| 30% | 83.2 / 0% | 78.6 / 44% | 19.1 / 89% |
| 40% | 79.8 / 8% | 55.0 / 42% | 21.1 / 75% |
| 50% | 70.2 / 25% | 55.2 / 38% | 25.9 / 62% |
| 60% | 59.9 / 32% | 50.7 / 47% | 29.9 / 53% |
| 70% | 61.9 / 27% | 50.9 / 41% | 45.4 / 45% |
| 80% | 57.6 / 36% | 51.2 / 40% | 51.2 / 40% |
| 90% | 58.5 / 36% | 50.9 / 43% | 58.5 / 36% |
| 100% | 57.6 / 39% | 57.6 / 39% | 57.6 / 39% |

## field, non-empty only (human h ≥ 0.1) (n=16)

Deployed gate e ≤ 0.55 keeps 16/16: kept median err 70.2 ml, rejected median err - ml. All readings: median 70.2 ml, 25% within 40 ml.

| coverage | entropy gate: median err / ≤40 ml | surface logit: median err / ≤40 ml | learned: median err / ≤40 ml |
|---|---|---|---|
| 20% | 83.2 / 0% | 80.0 / 33% | 29.9 / 67% |
| 30% | 83.2 / 0% | 80.0 / 20% | 51.2 / 40% |
| 40% | 79.8 / 0% | 79.3 / 33% | 63.8 / 33% |
| 50% | 70.2 / 12% | 79.3 / 38% | 63.8 / 25% |
| 60% | 78.6 / 10% | 68.9 / 30% | 77.5 / 20% |
| 70% | 76.4 / 18% | 59.3 / 36% | 76.4 / 18% |
| 80% | 64.0 / 23% | 59.3 / 31% | 76.4 / 15% |
| 90% | 70.2 / 21% | 67.8 / 29% | 70.2 / 21% |
| 100% | 70.2 / 25% | 70.2 / 25% | 70.2 / 25% |

