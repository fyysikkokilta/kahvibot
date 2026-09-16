# Model gym — 2026-09-10T08:19

Candidates scored on: the frozen blind hand-click set (99 records, Jan–Jun 2026 camera), the field set (400 pots on 208 kahviraspi frames from 2026-08-29..09-09, 31 with human surface clicks from the Telegram survey, 13 of those blind), and an archive day for coverage. Errors are |Δh|×1250 ml on the linear scale (the survey clicks give surface rows, not volumes).

## 1. Accuracy

| model | blind fill median ml | blind non-empty median ml | within 25 ml | field err median ml (n) | field non-empty err ml (n) | field err p90 ml |
|---|---|---|---|---|---|---|
| v9_s025_best | 45.5 | 58.43 | 0.273 | 63.5 (31) | 72.4 (16) | 144.9 |

## 2. Coverage at the entropy gate (share of pots that would be shown)

| model | set | median e | ≤0.55 | ≤0.58 | ≤0.60 | ≤0.62 | ≤0.65 | ≤0.70 |
|---|---|---|---|---|---|---|---|---|
| v9_s025_best | field (400 pots) | 0.290 | 96% | 96% | 96% | 96% | 96% | 96% |
| v9_s025_best | archive (293 pots) | 0.254 | 100% | 100% | 100% | 100% | 100% | 100% |

## 3. What each gate lets through on the field set (labelled pots)

Median |error| of kept vs rejected readings, all labelled pots and the non-empty subset (human h ≥ 0.1; empties are easy and inflate every pooled number). A gate that works keeps the accurate ones.

| model | gate | kept (err ml) | rejected (err ml) | kept non-empty (err ml) | rejected non-empty (err ml) |
|---|---|---|---|---|---|
| v9_s025_best | 0.55 | 31 (63.5) | 0 (None) | 16 (72.4) | 0 (None) |
| v9_s025_best | 0.58 | 31 (63.5) | 0 (None) | 16 (72.4) | 0 (None) |
| v9_s025_best | 0.60 | 31 (63.5) | 0 (None) | 16 (72.4) | 0 (None) |
| v9_s025_best | 0.62 | 31 (63.5) | 0 (None) | 16 (72.4) | 0 (None) |
| v9_s025_best | 0.65 | 31 (63.5) | 0 (None) | 16 (72.4) | 0 (None) |
| v9_s025_best | 0.70 | 31 (63.5) | 0 (None) | 16 (72.4) | 0 (None) |

## 4. Cost (identical trunk for all candidates)

| stage | local s | Pi-projected s |
|---|---|---|
| detect_s | 0.034 | 0.44 |
| read_tta1_s | 0.097 | 1.26 |
| read_tta8_s | 0.569 | 7.34 |

Training args differences and notes:

* **v9_s025_best** — same run, checkpoint selected on repeatability (step 600)
