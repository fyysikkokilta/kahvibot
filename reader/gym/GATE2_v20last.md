# Gate v2 — learned reliability score vs entropy gate

Model dir: _work/onnx_v20last. 'Good' = |Δh|·1250 ≤ 40 ml vs the human click. Logistic regression on e, h, d, u, v, luma, is_left, fitted on 158 archive-era train records; evaluated on 99 blind archive records and 31 field pots.

Standardised weights: `{"e": -0.216, "h": 0.591, "d": -0.185, "u": 0.345, "v": -0.329, "luma": 0.171, "is_left": 0.125}`

## blind archive (Jan–Jun 2026 camera) (n=99)

Deployed gate e ≤ 0.55 keeps 2/99: kept median err 21.3 ml, rejected median err 34.4 ml. All readings: median 33.8 ml, 55% within 40 ml.

| coverage | entropy gate: median err / ≤40 ml | surface logit: median err / ≤40 ml | learned: median err / ≤40 ml |
|---|---|---|---|
| 20% | 32.0 / 60% | 27.5 / 55% | 51.0 / 45% |
| 30% | 31.6 / 60% | 45.6 / 47% | 33.1 / 53% |
| 40% | 32.7 / 57% | 37.9 / 50% | 34.5 / 52% |
| 50% | 34.1 / 56% | 31.4 / 52% | 31.5 / 56% |
| 60% | 34.4 / 54% | 44.5 / 49% | 39.8 / 53% |
| 70% | 34.4 / 54% | 44.5 / 48% | 34.4 / 55% |
| 80% | 39.8 / 51% | 34.6 / 51% | 34.4 / 54% |
| 90% | 33.8 / 54% | 33.8 / 53% | 33.8 / 55% |
| 100% | 33.8 / 55% | 33.8 / 55% | 33.8 / 55% |

## blind archive, non-empty only (human h ≥ 0.1) (n=71)

Deployed gate e ≤ 0.55 keeps 1/71: kept median err 8.9 ml, rejected median err 46.2 ml. All readings: median 45.9 ml, 48% within 40 ml.

| coverage | entropy gate: median err / ≤40 ml | surface logit: median err / ≤40 ml | learned: median err / ≤40 ml |
|---|---|---|---|
| 20% | 47.7 / 36% | 24.1 / 57% | 60.3 / 36% |
| 30% | 48.7 / 38% | 27.6 / 52% | 46.6 / 48% |
| 40% | 47.7 / 39% | 45.6 / 46% | 33.1 / 54% |
| 50% | 47.7 / 42% | 30.7 / 53% | 45.2 / 47% |
| 60% | 46.6 / 44% | 44.5 / 49% | 34.6 / 51% |
| 70% | 47.7 / 44% | 31.4 / 52% | 45.2 / 48% |
| 80% | 48.7 / 44% | 44.5 / 49% | 34.6 / 51% |
| 90% | 45.2 / 48% | 45.2 / 48% | 33.1 / 52% |
| 100% | 45.9 / 48% | 45.9 / 48% | 45.9 / 48% |

## field (2026-09 camera, survey clicks) (n=31)

Deployed gate e ≤ 0.55 keeps 4/31: kept median err 33.4 ml, rejected median err 22.3 ml. All readings: median 22.3 ml, 58% within 40 ml.

| coverage | entropy gate: median err / ≤40 ml | surface logit: median err / ≤40 ml | learned: median err / ≤40 ml |
|---|---|---|---|
| 20% | 7.2 / 67% | 48.0 / 17% | 34.2 / 50% |
| 30% | 0.0 / 78% | 48.5 / 22% | 25.5 / 56% |
| 40% | 3.8 / 83% | 45.2 / 42% | 28.2 / 58% |
| 50% | 11.0 / 69% | 23.9 / 56% | 19.4 / 69% |
| 60% | 7.7 / 68% | 22.3 / 58% | 25.5 / 58% |
| 70% | 14.4 / 68% | 20.5 / 59% | 28.2 / 55% |
| 80% | 16.4 / 64% | 16.4 / 64% | 25.5 / 56% |
| 90% | 17.5 / 64% | 20.5 / 61% | 20.5 / 61% |
| 100% | 22.3 / 58% | 22.3 / 58% | 22.3 / 58% |

## field, non-empty only (human h ≥ 0.1) (n=16)

Deployed gate e ≤ 0.55 keeps 1/16: kept median err 286.3 ml, rejected median err 47.5 ml. All readings: median 48.0 ml, 38% within 40 ml.

| coverage | entropy gate: median err / ≤40 ml | surface logit: median err / ≤40 ml | learned: median err / ≤40 ml |
|---|---|---|---|
| 20% | 61.6 / 33% | 42.9 / 33% | 47.5 / 33% |
| 30% | 42.9 / 40% | 48.5 / 20% | 42.9 / 40% |
| 40% | 32.6 / 50% | 48.0 / 17% | 45.2 / 33% |
| 50% | 32.6 / 50% | 48.0 / 25% | 45.2 / 38% |
| 60% | 36.9 / 50% | 48.0 / 30% | 36.9 / 50% |
| 70% | 42.9 / 45% | 47.5 / 36% | 42.9 / 45% |
| 80% | 42.9 / 46% | 47.5 / 38% | 42.9 / 46% |
| 90% | 45.7 / 43% | 48.0 / 36% | 45.2 / 43% |
| 100% | 48.0 / 38% | 48.0 / 38% | 48.0 / 38% |

