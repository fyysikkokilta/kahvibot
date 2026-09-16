# Model gym — 2026-09-10T09:37

Candidates scored on: the frozen blind hand-click set (99 records, Jan–Jun 2026 camera), the field set (400 pots on 208 kahviraspi frames from 2026-08-29..09-09, 31 with human surface clicks from the Telegram survey, 13 of those blind), and an archive day for coverage. Errors are |Δh|×1250 ml on the linear scale (the survey clicks give surface rows, not volumes).

## 1. Accuracy

| model | blind fill median ml | blind non-empty median ml | within 25 ml | field err median ml (n) | field non-empty err ml (n) | field err p90 ml |
|---|---|---|---|---|---|---|
| v8 | 30.88 | 28.82 | 0.455 | 44.5 (31) | 49.8 (16) | 97.3 |
| v20last | 24.64 | 41.97 | 0.515 | 22.3 (31) | 48.0 (16) | 135.1 |
| v43last | 27.24 | 31.75 | 0.475 | 49.2 (31) | 45.3 (16) | 95.5 |
| v9ft_s05_last | 43.92 | 39.71 | 0.313 | 23.9 (31) | 89.1 (16) | 180.2 |
| v9ft_lr1e4_s025_last | 32.42 | 35.54 | 0.424 | 34.1 (31) | 54.2 (16) | 103.5 |
| v9ft_lr1e4_s01_last | 29.74 | 37.31 | 0.414 | 31.0 (31) | 41.6 (16) | 132.1 |
| v9ft_lr1e4_s0_last | 30.79 | 30.72 | 0.414 | 35.3 (31) | 43.7 (16) | 102.7 |
| v9_s025_last | 62.67 | 46.42 | 0.253 | 44.4 (31) | 111.6 (16) | 210.8 |

## 2. Coverage at the entropy gate (share of pots that would be shown)

| model | set | median e | ≤0.55 | ≤0.58 | ≤0.60 | ≤0.62 | ≤0.65 | ≤0.70 |
|---|---|---|---|---|---|---|---|---|
| v8 | field (400 pots) | 0.568 | 29% | 60% | 75% | 84% | 90% | 94% |
| v8 | archive (293 pots) | 0.553 | 47% | 78% | 94% | 96% | 97% | 99% |
| v20last | field (400 pots) | 0.592 | 15% | 34% | 60% | 76% | 88% | 93% |
| v20last | archive (293 pots) | 0.572 | 15% | 64% | 73% | 79% | 89% | 100% |
| v43last | field (400 pots) | 0.579 | 20% | 52% | 70% | 79% | 86% | 93% |
| v43last | archive (293 pots) | 0.549 | 51% | 78% | 83% | 86% | 92% | 100% |
| v9ft_s05_last | field (400 pots) | 0.179 | 96% | 97% | 97% | 97% | 97% | 97% |
| v9ft_s05_last | archive (293 pots) | 0.130 | 100% | 100% | 100% | 100% | 100% | 100% |
| v9ft_lr1e4_s025_last | field (400 pots) | 0.359 | 95% | 96% | 96% | 96% | 96% | 96% |
| v9ft_lr1e4_s025_last | archive (293 pots) | 0.336 | 100% | 100% | 100% | 100% | 100% | 100% |
| v9ft_lr1e4_s01_last | field (400 pots) | 0.464 | 87% | 92% | 94% | 95% | 96% | 96% |
| v9ft_lr1e4_s01_last | archive (293 pots) | 0.442 | 92% | 99% | 99% | 99% | 100% | 100% |
| v9ft_lr1e4_s0_last | field (400 pots) | 0.583 | 28% | 46% | 65% | 76% | 87% | 92% |
| v9ft_lr1e4_s0_last | archive (293 pots) | 0.576 | 13% | 53% | 78% | 94% | 97% | 98% |
| v9_s025_last | field (400 pots) | 0.127 | 96% | 96% | 96% | 96% | 96% | 97% |
| v9_s025_last | archive (293 pots) | 0.044 | 100% | 100% | 100% | 100% | 100% | 100% |

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
| v9ft_s05_last | 0.55 | 31 (23.9) | 0 (None) | 16 (89.1) | 0 (None) |
| v9ft_s05_last | 0.58 | 31 (23.9) | 0 (None) | 16 (89.1) | 0 (None) |
| v9ft_s05_last | 0.60 | 31 (23.9) | 0 (None) | 16 (89.1) | 0 (None) |
| v9ft_s05_last | 0.62 | 31 (23.9) | 0 (None) | 16 (89.1) | 0 (None) |
| v9ft_s05_last | 0.65 | 31 (23.9) | 0 (None) | 16 (89.1) | 0 (None) |
| v9ft_s05_last | 0.70 | 31 (23.9) | 0 (None) | 16 (89.1) | 0 (None) |
| v9ft_lr1e4_s025_last | 0.55 | 31 (34.1) | 0 (None) | 16 (54.2) | 0 (None) |
| v9ft_lr1e4_s025_last | 0.58 | 31 (34.1) | 0 (None) | 16 (54.2) | 0 (None) |
| v9ft_lr1e4_s025_last | 0.60 | 31 (34.1) | 0 (None) | 16 (54.2) | 0 (None) |
| v9ft_lr1e4_s025_last | 0.62 | 31 (34.1) | 0 (None) | 16 (54.2) | 0 (None) |
| v9ft_lr1e4_s025_last | 0.65 | 31 (34.1) | 0 (None) | 16 (54.2) | 0 (None) |
| v9ft_lr1e4_s025_last | 0.70 | 31 (34.1) | 0 (None) | 16 (54.2) | 0 (None) |
| v9ft_lr1e4_s01_last | 0.55 | 25 (39.1) | 6 (17.6) | 11 (46.8) | 5 (22.6) |
| v9ft_lr1e4_s01_last | 0.58 | 28 (31.9) | 3 (23.9) | 13 (42.9) | 3 (23.9) |
| v9ft_lr1e4_s01_last | 0.60 | 28 (31.9) | 3 (23.9) | 13 (42.9) | 3 (23.9) |
| v9ft_lr1e4_s01_last | 0.62 | 29 (31.0) | 2 (57.4) | 14 (41.6) | 2 (57.4) |
| v9ft_lr1e4_s01_last | 0.65 | 30 (30.2) | 1 (92.1) | 15 (40.2) | 1 (92.1) |
| v9ft_lr1e4_s01_last | 0.70 | 30 (30.2) | 1 (92.1) | 15 (40.2) | 1 (92.1) |
| v9ft_lr1e4_s0_last | 0.55 | 4 (26.3) | 27 (35.3) | 1 (286.3) | 15 (42.0) |
| v9ft_lr1e4_s0_last | 0.58 | 10 (38.7) | 21 (33.6) | 3 (56.5) | 13 (39.7) |
| v9ft_lr1e4_s0_last | 0.60 | 17 (35.3) | 14 (34.4) | 6 (68.2) | 10 (34.4) |
| v9ft_lr1e4_s0_last | 0.62 | 22 (30.0) | 9 (58.6) | 10 (43.7) | 6 (50.5) |
| v9ft_lr1e4_s0_last | 0.65 | 25 (33.6) | 6 (50.5) | 10 (43.7) | 6 (50.5) |
| v9ft_lr1e4_s0_last | 0.70 | 27 (35.3) | 4 (34.4) | 12 (51.0) | 4 (34.4) |
| v9_s025_last | 0.55 | 31 (44.4) | 0 (None) | 16 (111.6) | 0 (None) |
| v9_s025_last | 0.58 | 31 (44.4) | 0 (None) | 16 (111.6) | 0 (None) |
| v9_s025_last | 0.60 | 31 (44.4) | 0 (None) | 16 (111.6) | 0 (None) |
| v9_s025_last | 0.62 | 31 (44.4) | 0 (None) | 16 (111.6) | 0 (None) |
| v9_s025_last | 0.65 | 31 (44.4) | 0 (None) | 16 (111.6) | 0 (None) |
| v9_s025_last | 0.70 | 31 (44.4) | 0 (None) | 16 (111.6) | 0 (None) |

## 4. Cost (identical trunk for all candidates)

| stage | local s | Pi-projected s |
|---|---|---|
| detect_s | 0.034 | 0.43 |
| read_tta1_s | 0.095 | 1.23 |
| read_tta8_s | 0.552 | 7.12 |

Training args differences and notes:

* **v8** — deployed
* **v20last** — v8 recipe + unlabelled invariance 0.5
* **v43last** — v8 recipe, pair-frac 0.506
* **v9ft_s05_last** — fine-tune lr 3e-4 sharp 0.5
* **v9ft_lr1e4_s025_last** — fine-tune lr 1e-4 sharp 0.25
* **v9ft_lr1e4_s01_last** — fine-tune lr 1e-4 sharp 0.10
* **v9ft_lr1e4_s0_last** — CONTROL fine-tune lr 1e-4, no sharpness
* **v9_s025_last** — scratch 3000 steps sharp 0.25
