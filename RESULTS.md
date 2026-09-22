# Results

## Run: full LexGLUE test, 2026-09-21

- Model: `typesafe/jev-1.13` (resolved `typesafe/jev-1.13-20260917` for every response)
- Protocol: zero-shot, `lexglue-systemone-v1`, threshold 0.5, `--max-chars 48000`
- Coverage: 23,607 / 23,607 scored, 0 failed. One relaunch after two HTTP 520s (retried).
- Cost: $4.02 reported by OpenRouter (pre-run estimate $3.98 ± 0.14 from n=50/task)
- Truncated inputs: SCOTUS 613/1400, EUR-LEX 266/5000, ECtHR A/B 20/1000 each

## F1 against published fine-tuned baselines

Baselines: [LexGLUE leaderboard](https://github.com/coastalcph/lex-glue#leaderboard),
medium-sized models, mean of 5 seeds, fine-tuned on each training set. Jev intervals: 95%
bootstrap over test examples (300 resamples). The leaderboard gives no intervals.

| Task | Jev μ-F1 [95% CI] | BERT | Legal-BERT | Jev m-F1 [95% CI] | BERT | Legal-BERT |
|---|---|---:|---:|---|---:|---:|
| ECtHR A | 73.0 [71.2, 74.9] | 71.2 | 70.0 | 71.4 [67.6, 74.6] | 63.6 | 64.0 |
| ECtHR B | 75.4 [74.0, 77.0] | 79.7 | 80.4 | 72.6 [68.8, 75.4] | 73.4 | 74.7 |
| SCOTUS | 72.6 [70.2, 75.4] | 68.3 | 76.4 | 62.1 [58.6, 65.3] | 58.3 | 66.5 |
| EUR-LEX | 39.1 [38.8, 39.4] | 71.4 | 72.1 | 37.0 [36.2, 37.6] | 57.2 | 57.4 |
| LEDGAR | 75.3 [74.5, 76.1] | 87.6 | 88.2 | 63.3 [61.9, 64.3] | 81.8 | 83.0 |
| UNFAIR-ToS | 76.4 [74.3, 78.5] | 95.6 | 96.0 | 54.4 [50.5, 58.0] | 81.3 | 83.0 |
| CaseHOLD | 77.3 [75.9, 78.6] | 70.8 | 75.3 | 77.3 | 70.8 | 75.3 |
| Arithmetic mean | 69.9 | 77.8 | 79.8 | 62.6 | 69.5 | 72.0 |
| Harmonic mean | 66.3 | 76.7 | 78.9 | 59.3 | 68.2 | 70.8 |

## Agreement with gold, calibration, and ranking (Jev only)

`jev-bench analyze --source jev=results/full-test/predictions.jsonl --output analysis/full-test.json`.
Kappa CIs: 95% bootstrap, 1000 resamples, seed 0. Multi-label kappa is Cohen's kappa per
label column, averaged over the task's real labels (no synthetic none-of-the-above column).
ECE: 10 equal-width bins; for choice tasks over the chosen label's probability, for
multi-label tasks over every (example, label) noul probability.

Single-label tasks:

| Task | n | Accuracy | Cohen's κ [95% CI] | MCC | Top-3 acc. | Mean confidence | ECE | Brier |
|---|---:|---:|---|---:|---:|---:|---:|---:|
| SCOTUS | 1400 | 0.726 | 0.670 [0.642, 0.698] | 0.672 | 0.897 | 0.873 | 0.148 | 0.428 |
| LEDGAR | 10000 | 0.753 | 0.748 [0.740, 0.757] | 0.749 | 0.903 | 0.869 | 0.116 | 0.368 |
| CaseHOLD | 3600 | 0.773 | 0.716 [0.698, 0.734] | 0.717 | 0.968 | 0.810 | 0.038 | 0.302 |

Multi-label tasks:

| Task | n | Macro label κ [95% CI] | Pooled κ | Micro precision | Micro recall | Pred. / gold labels per doc | Macro ROC-AUC | ECE |
|---|---:|---|---:|---:|---:|---:|---:|---:|
| ECtHR A | 1000 | 0.716 [0.672, 0.751] | 0.727 | 0.644 | 0.934 | 1.58 / 1.09 | 0.974 | 0.082 |
| ECtHR B | 1000 | 0.681 [0.650, 0.706] | 0.706 | 0.644 | 0.913 | 2.03 / 1.44 | 0.951 | 0.096 |
| EUR-LEX | 5000 | 0.337 [0.330, 0.343] | 0.347 | 0.294 | 0.583 | 10.09 / 5.08 | 0.902 | 0.099 |
| UNFAIR-ToS | 1607 | 0.493 [0.447, 0.533] | 0.425 | 0.287 | 0.925 | 0.37 / 0.12 | 0.992 | 0.073 |

Findings:

- **Multi-label errors are mostly over-prediction.** On all four multi-label tasks Jev
  predicts 1.4x to 3.2x as many labels as gold. Recall is high (0.91 to 0.93 on ECtHR and
  UNFAIR-ToS) and precision low (0.29 to 0.64). Ranking is strong: macro ROC-AUC 0.90 to 0.99.
  The deficit is in the fixed 0.5 cut-off, not in the ordering of labels.
- **UNFAIR-ToS micro-F1 is carried by the none-of-the-above column.** Upstream scoring adds
  a synthetic column for sentences with no unfair term (1435/1607 = 89% of test sentences). Over the 8
  real categories alone, Jev's micro-F1 is 2PR/(P+R) = 0.44. The published baselines are
  scored the same way, so the leaderboard comparison stays like-for-like, but 76.4 overstates
  how well Jev finds unfair clauses.
- **Choice probabilities are over-confident on SCOTUS and LEDGAR** (mean confidence 0.87 vs.
  accuracy 0.73/0.75; ECE 0.15/0.12). CaseHOLD is close to calibrated (ECE 0.04). The correct
  label is in the top 3 for 90% to 97% of documents.
- **Length:** LEDGAR, UNFAIR-ToS, and ECtHR A lose 7 to 16 micro-F1 points from the shortest
  to the longest length quartile (breakdown in `analysis/full-test.json`). SCOTUS truncated
  documents score no worse than untruncated ones (74.4 vs 71.2 μ-F1, n=613/787).

### Oracle threshold (diagnostic only, not a result)

The best single global threshold chosen on the *test* labels. Tuning on test data is not a
valid protocol; this bounds what validation-set threshold tuning could recover.

| Task | Oracle threshold | μ-F1 at 0.5 | μ-F1 at oracle | m-F1 at 0.5 | m-F1 at oracle |
|---|---:|---:|---:|---:|---:|
| ECtHR A | 0.60 | 73.0 | 74.3 | 71.4 | 72.4 |
| ECtHR B | 0.75 | 75.4 | 80.2 | 72.6 | 75.5 |
| EUR-LEX | 0.65 | 39.1 | 40.0 | 37.0 | 35.9 |
| UNFAIR-ToS | 0.90 | 76.4 | 90.6 | 54.4 | 35.2 |

A global threshold does not close the EUR-LEX gap (+0.9 μ-F1 at best). On UNFAIR-ToS it
trades macro-F1 for micro-F1, so per-label thresholds tuned on validation are the candidate
next step there.

## Paired comparison with BERT

Pending: BERT-base reproduction with the upstream scripts on Modal (`bert/`), one seed per
task, to measure inter-model kappa, McNemar tests, and paired F1 differences on the same
test examples.
