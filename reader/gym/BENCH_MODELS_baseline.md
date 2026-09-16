# Model gym — 2026-09-09T23:07

Candidates scored on: the frozen blind hand-click set (99 records, Jan–Jun 2026 camera), the field set (400 pots on 208 kahviraspi frames from 2026-08-29..09-09, 31 with human surface clicks from the Telegram survey, 13 of those blind), and an archive day for coverage. Errors are |Δh|×1250 ml on the linear scale (the survey clicks give surface rows, not volumes).

## 1. Accuracy

| model | blind fill median ml | blind non-empty median ml | within 25 ml | field err median ml (n) | field non-empty err ml (n) | field err p90 ml |
|---|---|---|---|---|---|---|
| v8 | 30.88 | 28.82 | 0.455 | 44.5 (31) | 49.8 (16) | 97.3 |
| v18 | 25.5 | 34.81 | 0.495 | 53.0 (31) | 86.1 (16) | 122.6 |
| v20last | 24.64 | 41.97 | 0.515 | 22.3 (31) | 48.0 (16) | 135.1 |
| v43last | 27.24 | 31.75 | 0.475 | 49.2 (31) | 45.3 (16) | 95.5 |

## 2. Coverage at the entropy gate (share of pots that would be shown)

| model | set | median e | ≤0.55 | ≤0.58 | ≤0.60 | ≤0.62 | ≤0.65 | ≤0.70 |
|---|---|---|---|---|---|---|---|---|
| v8 | field (400 pots) | 0.568 | 29% | 60% | 75% | 84% | 90% | 94% |
| v8 | archive (293 pots) | 0.553 | 47% | 78% | 94% | 96% | 97% | 99% |
| v18 | field (400 pots) | 0.571 | 28% | 58% | 73% | 80% | 84% | 90% |
| v18 | archive (293 pots) | 0.531 | 75% | 100% | 100% | 100% | 100% | 100% |
| v20last | field (400 pots) | 0.592 | 15% | 34% | 60% | 76% | 88% | 93% |
| v20last | archive (293 pots) | 0.572 | 15% | 64% | 73% | 79% | 89% | 100% |
| v43last | field (400 pots) | 0.579 | 20% | 52% | 70% | 79% | 86% | 93% |
| v43last | archive (293 pots) | 0.549 | 51% | 78% | 83% | 86% | 92% | 100% |

## 3. What each gate lets through on the field set (labelled pots)

Median |error| of kept vs rejected readings, all labelled pots and the non-empty subset (human h ≥ 0.1; empties are easy and inflate every pooled number). A gate that works keeps the accurate ones.

| model | gate | kept (err ml) | rejected (err ml) | kept non-empty (err ml) | rejected non-empty (err ml) |
|---|---|---|---|---|---|
| v8 | 0.55 | 8 (51.4) | 23 (29.2) | 2 (221.9) | 14 (45.7) |
| v8 | 0.58 | 16 (46.8) | 15 (24.7) | 6 (52.6) | 10 (38.5) |
| v8 | 0.60 | 21 (44.5) | 10 (38.9) | 7 (46.5) | 9 (53.1) |
| v8 | 0.62 | 25 (44.8) | 6 (23.7) | 10 (55.9) | 6 (23.7) |
| v8 | 0.65 | 27 (44.8) | 4 (23.7) | 12 (55.9) | 4 (23.7) |
| v8 | 0.70 | 29 (44.5) | 2 (49.4) | 14 (49.8) | 2 (49.4) |
| v18 | 0.55 | 8 (51.9) | 23 (53.7) | 1 (237.0) | 15 (84.4) |
| v18 | 0.58 | 14 (52.3) | 17 (55.1) | 2 (121.3) | 14 (86.1) |
| v18 | 0.60 | 21 (50.8) | 10 (86.1) | 7 (22.2) | 9 (87.7) |
| v18 | 0.62 | 23 (50.8) | 8 (87.8) | 8 (53.3) | 8 (87.8) |
| v18 | 0.65 | 24 (51.2) | 7 (87.7) | 9 (84.4) | 7 (87.7) |
| v18 | 0.70 | 26 (52.3) | 5 (87.7) | 11 (84.4) | 5 (87.7) |
| v20last | 0.55 | 4 (33.4) | 27 (22.3) | 1 (286.3) | 15 (47.5) |
| v20last | 0.58 | 9 (0.0) | 22 (36.9) | 1 (286.3) | 15 (47.5) |
| v20last | 0.60 | 15 (7.7) | 16 (45.2) | 2 (154.3) | 14 (48.0) |
| v20last | 0.62 | 19 (7.7) | 12 (48.0) | 5 (42.9) | 11 (48.5) |
| v20last | 0.65 | 23 (14.4) | 8 (75.7) | 9 (31.0) | 7 (102.9) |
| v20last | 0.70 | 28 (17.5) | 3 (102.9) | 13 (42.9) | 3 (102.9) |
| v43last | 0.55 | 9 (50.6) | 22 (47.0) | 1 (242.3) | 15 (39.8) |
| v43last | 0.58 | 12 (49.9) | 19 (39.8) | 1 (242.3) | 15 (39.8) |
| v43last | 0.60 | 15 (49.2) | 16 (45.3) | 2 (124.0) | 14 (45.3) |
| v43last | 0.62 | 21 (49.2) | 10 (45.3) | 6 (63.7) | 10 (45.3) |
| v43last | 0.65 | 27 (50.6) | 4 (32.6) | 12 (73.6) | 4 (32.6) |
| v43last | 0.70 | 30 (49.9) | 1 (19.3) | 15 (50.7) | 1 (19.3) |

## 4. Cost (identical trunk for all candidates)

| stage | local s | Pi-projected s |
|---|---|---|
| detect_s | 0.045 | 0.58 |
| read_tta1_s | 0.131 | 1.69 |
| read_tta8_s | 0.762 | 9.83 |

Training args differences and notes:

* **v8** — deployed model; resnet18 trunk, 3000 steps, hand-share 0.25, surf-weight 1.0
* **v18** — v8 recipe, seed 1
* **v20last** — v8 recipe + w_unlab_invar 0.5, last checkpoint
* **v43last** — v8 recipe with pair-frac 0.506 ablation, last checkpoint
