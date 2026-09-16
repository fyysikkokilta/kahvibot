# Gate v2 — learned reliability score vs entropy gate

Model dir: _work/onnx_v9ft_lr1e4_s0_last. 'Good' = |Δh|·1250 ≤ 40 ml vs the human click. Logistic regression on e, h, d, u, v, luma, is_left, fitted on 158 archive-era train records; evaluated on 99 blind archive records and 31 field pots.

Standardised weights: `{"e": -0.109, "h": -0.394, "d": 0.125, "u": 0.012, "v": -0.429, "luma": 0.449, "is_left": 0.096}`

## blind archive (Jan–Jun 2026 camera) (n=99)

Deployed gate e ≤ 0.55 keeps 10/99: kept median err 28.8 ml, rejected median err 31.7 ml. All readings: median 31.7 ml, 65% within 40 ml.

| coverage | entropy gate: median err / ≤40 ml | surface logit: median err / ≤40 ml | learned: median err / ≤40 ml |
|---|---|---|---|
| 20% | 31.7 / 80% | 34.3 / 55% | 26.5 / 95% |
| 30% | 31.0 / 80% | 35.0 / 53% | 28.8 / 83% |
| 40% | 31.0 / 78% | 37.5 / 52% | 29.0 / 78% |
| 50% | 31.3 / 74% | 36.8 / 56% | 27.5 / 76% |
| 60% | 31.3 / 73% | 33.4 / 59% | 29.0 / 73% |
| 70% | 31.3 / 70% | 34.5 / 59% | 29.1 / 71% |
| 80% | 31.3 / 68% | 32.0 / 62% | 31.3 / 66% |
| 90% | 30.7 / 69% | 32.1 / 62% | 31.6 / 65% |
| 100% | 31.7 / 65% | 31.7 / 65% | 31.7 / 65% |

## blind archive, non-empty only (human h ≥ 0.1) (n=71)

Deployed gate e ≤ 0.55 keeps 2/71: kept median err 55.2 ml, rejected median err 36.7 ml. All readings: median 36.8 ml, 54% within 40 ml.

| coverage | entropy gate: median err / ≤40 ml | surface logit: median err / ≤40 ml | learned: median err / ≤40 ml |
|---|---|---|---|
| 20% | 37.6 / 50% | 34.2 / 57% | 41.8 / 43% |
| 30% | 34.5 / 57% | 30.7 / 57% | 34.5 / 52% |
| 40% | 35.6 / 57% | 35.0 / 54% | 37.6 / 50% |
| 50% | 35.6 / 56% | 37.5 / 53% | 35.6 / 53% |
| 60% | 37.9 / 51% | 36.8 / 56% | 33.4 / 56% |
| 70% | 37.3 / 52% | 35.0 / 58% | 37.0 / 52% |
| 80% | 33.4 / 56% | 33.4 / 58% | 36.7 / 54% |
| 90% | 33.9 / 56% | 35.6 / 56% | 35.6 / 55% |
| 100% | 36.8 / 54% | 36.8 / 54% | 36.8 / 54% |

## field (2026-09 camera, survey clicks) (n=31)

Deployed gate e ≤ 0.55 keeps 4/31: kept median err 26.3 ml, rejected median err 35.3 ml. All readings: median 35.3 ml, 55% within 40 ml.

| coverage | entropy gate: median err / ≤40 ml | surface logit: median err / ≤40 ml | learned: median err / ≤40 ml |
|---|---|---|---|
| 20% | 24.8 / 50% | 34.4 / 67% | 30.1 / 67% |
| 30% | 35.3 / 56% | 29.1 / 67% | 35.3 / 56% |
| 40% | 29.9 / 58% | 27.8 / 67% | 29.3 / 67% |
| 50% | 34.5 / 56% | 34.4 / 56% | 34.5 / 56% |
| 60% | 33.6 / 58% | 29.1 / 58% | 35.3 / 53% |
| 70% | 30.0 / 59% | 34.4 / 55% | 38.5 / 50% |
| 80% | 33.6 / 56% | 33.6 / 56% | 35.3 / 52% |
| 90% | 37.5 / 54% | 36.6 / 54% | 37.5 / 54% |
| 100% | 35.3 / 55% | 35.3 / 55% | 35.3 / 55% |

## field, non-empty only (human h ≥ 0.1) (n=16)

Deployed gate e ≤ 0.55 keeps 1/16: kept median err 286.3 ml, rejected median err 42.0 ml. All readings: median 43.7 ml, 44% within 40 ml.

| coverage | entropy gate: median err / ≤40 ml | surface logit: median err / ≤40 ml | learned: median err / ≤40 ml |
|---|---|---|---|
| 20% | 56.5 / 0% | 26.5 / 67% | 144.5 / 0% |
| 30% | 56.5 / 20% | 29.1 / 60% | 80.0 / 0% |
| 40% | 68.2 / 17% | 34.4 / 67% | 68.2 / 17% |
| 50% | 49.2 / 38% | 34.4 / 62% | 51.0 / 25% |
| 60% | 43.7 / 40% | 34.4 / 60% | 51.0 / 30% |
| 70% | 45.4 / 36% | 29.1 / 64% | 56.5 / 27% |
| 80% | 45.4 / 38% | 39.7 / 54% | 45.4 / 38% |
| 90% | 43.7 / 43% | 40.8 / 50% | 51.0 / 36% |
| 100% | 43.7 / 44% | 43.7 / 44% | 43.7 / 44% |

