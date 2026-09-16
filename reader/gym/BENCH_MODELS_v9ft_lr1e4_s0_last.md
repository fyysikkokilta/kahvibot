# Model gym — 2026-09-10T09:31

Candidates scored on: the frozen blind hand-click set (99 records, Jan–Jun 2026 camera), the field set (400 pots on 208 kahviraspi frames from 2026-08-29..09-09, 31 with human surface clicks from the Telegram survey, 13 of those blind), and an archive day for coverage. Errors are |Δh|×1250 ml on the linear scale (the survey clicks give surface rows, not volumes).

## 1. Accuracy

| model | blind fill median ml | blind non-empty median ml | within 25 ml | field err median ml (n) | field non-empty err ml (n) | field err p90 ml |
|---|---|---|---|---|---|---|
| v9ft_lr1e4_s0_last | 30.79 | 30.72 | 0.414 | 35.3 (31) | 43.7 (16) | 102.7 |

## 2. Coverage at the entropy gate (share of pots that would be shown)

| model | set | median e | ≤0.55 | ≤0.58 | ≤0.60 | ≤0.62 | ≤0.65 | ≤0.70 |
|---|---|---|---|---|---|---|---|---|
| v9ft_lr1e4_s0_last | field (400 pots) | 0.583 | 28% | 46% | 65% | 76% | 87% | 92% |
| v9ft_lr1e4_s0_last | archive (293 pots) | 0.576 | 13% | 53% | 78% | 94% | 97% | 98% |

## 3. What each gate lets through on the field set (labelled pots)

Median |error| of kept vs rejected readings, all labelled pots and the non-empty subset (human h ≥ 0.1; empties are easy and inflate every pooled number). A gate that works keeps the accurate ones.

| model | gate | kept (err ml) | rejected (err ml) | kept non-empty (err ml) | rejected non-empty (err ml) |
|---|---|---|---|---|---|
| v9ft_lr1e4_s0_last | 0.55 | 4 (26.3) | 27 (35.3) | 1 (286.3) | 15 (42.0) |
| v9ft_lr1e4_s0_last | 0.58 | 10 (38.7) | 21 (33.6) | 3 (56.5) | 13 (39.7) |
| v9ft_lr1e4_s0_last | 0.60 | 17 (35.3) | 14 (34.4) | 6 (68.2) | 10 (34.4) |
| v9ft_lr1e4_s0_last | 0.62 | 22 (30.0) | 9 (58.6) | 10 (43.7) | 6 (50.5) |
| v9ft_lr1e4_s0_last | 0.65 | 25 (33.6) | 6 (50.5) | 10 (43.7) | 6 (50.5) |
| v9ft_lr1e4_s0_last | 0.70 | 27 (35.3) | 4 (34.4) | 12 (51.0) | 4 (34.4) |

## 4. Cost (identical trunk for all candidates)

| stage | local s | Pi-projected s |
|---|---|---|
| detect_s | 0.034 | 0.44 |
| read_tta1_s | 0.097 | 1.25 |
| read_tta8_s | 0.556 | 7.18 |

Training args differences and notes:

* **v9ft_lr1e4_s0_last** — CONTROL: fine-tune of v8, lr 1e-4, 1200 steps, no sharpness
