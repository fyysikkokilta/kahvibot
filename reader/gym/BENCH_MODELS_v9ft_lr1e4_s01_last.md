# Model gym — 2026-09-10T01:28

Candidates scored on: the frozen blind hand-click set (99 records, Jan–Jun 2026 camera), the field set (400 pots on 208 kahviraspi frames from 2026-08-29..09-09, 31 with human surface clicks from the Telegram survey, 13 of those blind), and an archive day for coverage. Errors are |Δh|×1250 ml on the linear scale (the survey clicks give surface rows, not volumes).

## 1. Accuracy

| model | blind fill median ml | blind non-empty median ml | within 25 ml | field err median ml (n) | field non-empty err ml (n) | field err p90 ml |
|---|---|---|---|---|---|---|
| v9ft_lr1e4_s01_last | 29.74 | 37.31 | 0.414 | 31.0 (31) | 41.6 (16) | 132.1 |

## 2. Coverage at the entropy gate (share of pots that would be shown)

| model | set | median e | ≤0.55 | ≤0.58 | ≤0.60 | ≤0.62 | ≤0.65 | ≤0.70 |
|---|---|---|---|---|---|---|---|---|
| v9ft_lr1e4_s01_last | field (400 pots) | 0.464 | 87% | 92% | 94% | 95% | 96% | 96% |
| v9ft_lr1e4_s01_last | archive (293 pots) | 0.442 | 92% | 99% | 99% | 99% | 100% | 100% |

## 3. What each gate lets through on the field set (labelled pots)

Median |error| of kept vs rejected readings, all labelled pots and the non-empty subset (human h ≥ 0.1; empties are easy and inflate every pooled number). A gate that works keeps the accurate ones.

| model | gate | kept (err ml) | rejected (err ml) | kept non-empty (err ml) | rejected non-empty (err ml) |
|---|---|---|---|---|---|
| v9ft_lr1e4_s01_last | 0.55 | 25 (39.1) | 6 (17.6) | 11 (46.8) | 5 (22.6) |
| v9ft_lr1e4_s01_last | 0.58 | 28 (31.9) | 3 (23.9) | 13 (42.9) | 3 (23.9) |
| v9ft_lr1e4_s01_last | 0.60 | 28 (31.9) | 3 (23.9) | 13 (42.9) | 3 (23.9) |
| v9ft_lr1e4_s01_last | 0.62 | 29 (31.0) | 2 (57.4) | 14 (41.6) | 2 (57.4) |
| v9ft_lr1e4_s01_last | 0.65 | 30 (30.2) | 1 (92.1) | 15 (40.2) | 1 (92.1) |
| v9ft_lr1e4_s01_last | 0.70 | 30 (30.2) | 1 (92.1) | 15 (40.2) | 1 (92.1) |

## 4. Cost (identical trunk for all candidates)

| stage | local s | Pi-projected s |
|---|---|---|
| detect_s | 0.033 | 0.43 |
| read_tta1_s | 0.094 | 1.21 |
| read_tta8_s | 0.551 | 7.11 |

Training args differences and notes:

* **v9ft_lr1e4_s01_last** — fine-tune of v8: lr 1e-4, w-sharp 0.10, 1200 steps, last
