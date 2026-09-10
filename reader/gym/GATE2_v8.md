# Gate v2 — learned reliability score vs entropy gate

Model dir: _work/onnx_v8. 'Good' = |Δh|·1250 ≤ 40 ml vs the human click. Logistic regression on e, h, d, u, v, luma, is_left, fitted on 158 archive-era train records; evaluated on 99 blind archive records and 31 field pots.

Standardised weights: `{"e": -0.893, "h": -0.668, "d": 0.161, "u": -0.087, "v": 0.227, "luma": 0.311, "is_left": 0.135}`

## blind archive (Jan–Jun 2026 camera) (n=99)

Deployed gate e ≤ 0.55 keeps 24/99: kept median err 26.7 ml, rejected median err 23.5 ml. All readings: median 25.5 ml, 69% within 40 ml.

| coverage | entropy gate: median err / ≤40 ml | surface logit: median err / ≤40 ml | learned: median err / ≤40 ml |
|---|---|---|---|
| 20% | 25.8 / 80% | 14.5 / 65% | 26.1 / 85% |
| 30% | 26.7 / 77% | 20.6 / 63% | 24.7 / 87% |
| 40% | 25.2 / 80% | 23.2 / 60% | 24.7 / 82% |
| 50% | 25.2 / 78% | 24.0 / 60% | 23.7 / 80% |
| 60% | 23.5 / 78% | 24.5 / 64% | 23.0 / 81% |
| 70% | 22.4 / 80% | 24.5 / 67% | 22.4 / 80% |
| 80% | 23.5 / 75% | 24.8 / 68% | 23.0 / 75% |
| 90% | 24.5 / 73% | 24.9 / 69% | 23.5 / 74% |
| 100% | 25.5 / 69% | 25.5 / 69% | 25.5 / 69% |

## blind archive, non-empty only (human h ≥ 0.1) (n=71)

Deployed gate e ≤ 0.55 keeps 8/71: kept median err 40.7 ml, rejected median err 26.1 ml. All readings: median 32.0 ml, 59% within 40 ml.

| coverage | entropy gate: median err / ≤40 ml | surface logit: median err / ≤40 ml | learned: median err / ≤40 ml |
|---|---|---|---|
| 20% | 40.7 / 50% | 14.5 / 64% | 34.7 / 64% |
| 30% | 26.1 / 67% | 18.2 / 62% | 24.5 / 71% |
| 40% | 25.0 / 68% | 20.6 / 64% | 25.3 / 71% |
| 50% | 24.0 / 67% | 21.8 / 64% | 23.2 / 72% |
| 60% | 23.0 / 72% | 23.0 / 63% | 23.5 / 70% |
| 70% | 24.0 / 66% | 23.2 / 62% | 24.0 / 66% |
| 80% | 25.5 / 65% | 24.5 / 65% | 24.5 / 65% |
| 90% | 25.8 / 64% | 25.0 / 64% | 25.8 / 64% |
| 100% | 32.0 / 59% | 32.0 / 59% | 32.0 / 59% |

## field (2026-09 camera, survey clicks) (n=31)

Deployed gate e ≤ 0.55 keeps 8/31: kept median err 51.4 ml, rejected median err 29.2 ml. All readings: median 44.5 ml, 48% within 40 ml.

| coverage | entropy gate: median err / ≤40 ml | surface logit: median err / ≤40 ml | learned: median err / ≤40 ml |
|---|---|---|---|
| 20% | 37.8 / 50% | 58.6 / 33% | 40.2 / 50% |
| 30% | 47.1 / 33% | 44.8 / 44% | 24.7 / 56% |
| 40% | 51.4 / 33% | 34.3 / 50% | 35.9 / 50% |
| 50% | 46.8 / 38% | 34.8 / 50% | 28.7 / 56% |
| 60% | 44.8 / 47% | 44.8 / 47% | 44.5 / 47% |
| 70% | 44.7 / 45% | 26.9 / 55% | 44.7 / 45% |
| 80% | 44.8 / 44% | 24.7 / 56% | 44.8 / 44% |
| 90% | 44.7 / 46% | 28.7 / 54% | 44.7 / 46% |
| 100% | 44.5 / 48% | 44.5 / 48% | 44.5 / 48% |

## field, non-empty only (human h ≥ 0.1) (n=16)

Deployed gate e ≤ 0.55 keeps 2/16: kept median err 221.9 ml, rejected median err 45.7 ml. All readings: median 49.8 ml, 38% within 40 ml.

| coverage | entropy gate: median err / ≤40 ml | surface logit: median err / ≤40 ml | learned: median err / ≤40 ml |
|---|---|---|---|
| 20% | 165.1 / 0% | 53.1 / 33% | 165.1 / 0% |
| 30% | 58.7 / 0% | 53.1 / 40% | 58.7 / 0% |
| 40% | 52.6 / 17% | 58.6 / 33% | 52.6 / 17% |
| 50% | 49.8 / 25% | 49.0 / 38% | 49.8 / 25% |
| 60% | 55.9 / 20% | 34.3 / 50% | 55.9 / 20% |
| 70% | 53.1 / 27% | 44.8 / 45% | 53.1 / 27% |
| 80% | 53.1 / 31% | 46.5 / 38% | 53.1 / 31% |
| 90% | 49.8 / 36% | 45.7 / 43% | 49.8 / 36% |
| 100% | 49.8 / 38% | 49.8 / 38% | 49.8 / 38% |

