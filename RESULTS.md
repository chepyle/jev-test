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

## Paired comparison with a reproduced BERT-base baseline

### Reproduction

BERT-base fine-tuned with the upstream `coastalcph/lex-glue` scripts (commit `419a49d`) on
Modal A100-40GB, one seed (1) per task; the leaderboard is a 5-seed mean. Cost: $21.58.
All code changes are in `bert/patch_upstream.py`; per-example test logits are in
`results/bert-seed1/` (gitignored), predictions exported with `bert/export_predictions.py`.

| Task | Reproduced μ-F1 / m-F1 | Published BERT | Epochs (early stop) |
|---|---|---|---:|
| ECtHR A | 70.3 / 61.9 | 71.2 / 63.6 | 7 |
| ECtHR B | 78.6 / 72.5 | 79.7 / 73.4 | 7 |
| SCOTUS | 67.2 / 60.7 | 68.3 / 58.3 | 10 |
| EUR-LEX | 71.6 / 56.5 | 71.4 / 57.2 | 11 |
| LEDGAR | 88.0 / 82.4 | 87.6 / 81.8 | 15 |
| UNFAIR-ToS | 95.2 / 80.0 | 95.6 / 81.3 | 12 |
| CaseHOLD | 70.8 | 70.8 | 4 |

Every task is within 1.1 μ-F1 of the published mean (m-F1 within 2.4), so the reproduction
stands in for the leaderboard BERT. Deviations from running the scripts as published:

- **Eager attention for ECtHR/SCOTUS.** transformers 4.44 defaults BERT to SDPA, which
  returns NaN for HierarchicalBert's all-padding segments (verified on real ECtHR cases:
  `modal run bert/lexglue_modal.py::trace`). Upstream's transformers 4.9 had only eager.
- **EUR-LEX trained up to 20 epochs.** `run_eurlex.sh` says 2 (set in commit `e7a46c9`
  alongside `GPU_NUMBER=6`); the maintainer reports 8 to 16 epochs for the published runs
  (coastalcph/lex-glue#21). Null result kept: the 2-epoch run scored **66.5 / 33.9**.
- **ECtHR A test logits recomputed under fp16 autocast.** `--fp16_full_eval` casts the
  model to half precision after training; 9510/10000 ECtHR A test logits came back NaN
  (scored 19.9 / 12.2). Recomputing from the saved best model reproduces its logged
  validation μ/m-F1 exactly (0.706 / 0.643). No other task had NaN or inf logits.
- **SCOTUS head has 14 outputs** (`label_list = range(14)`) for 13 released classes; the
  unused column never wins the argmax and is dropped at export.

### Agreement with gold: Jev vs BERT

Cohen's κ against gold (per-label mean for multi-label tasks), 95% bootstrap CI, n as above.

| Task | Jev κ | BERT κ | Jev ECE | BERT ECE |
|---|---|---|---:|---:|
| ECtHR A | **0.716** [0.672, 0.751] | 0.617 [0.575, 0.655] | 0.082 | 0.032 |
| ECtHR B | 0.681 [0.650, 0.706] | 0.710 [0.676, 0.738] | 0.096 | 0.034 |
| SCOTUS | **0.670** [0.642, 0.698] | 0.611 [0.583, 0.640] | 0.148 | 0.259 |
| EUR-LEX | 0.337 [0.330, 0.343] | **0.551** [0.538, 0.560] | 0.099 | 0.012 |
| LEDGAR | 0.748 [0.740, 0.757] | **0.877** [0.871, 0.884] | 0.116 | 0.109 |
| UNFAIR-ToS | 0.493 [0.447, 0.533] | **0.775** [0.711, 0.824] | 0.073 | 0.005 |
| CaseHOLD | **0.716** [0.698, 0.734] | 0.635 [0.618, 0.653] | 0.038 | 0.049 |

Bold marks non-overlapping intervals. ECtHR B intervals overlap.

### Paired comparison on identical test examples

`jev-bench analyze --source jev=... --source bert=...` → `analysis/jev-vs-bert.json`.
ΔF1 = Jev − BERT, paired bootstrap (1000 resamples, seed 0). McNemar: exact binomial test on
examples where exactly one model is fully correct (whole label set for multi-label tasks).

| Task | Inter-model κ | Same prediction | Only Jev right | Only BERT right | McNemar p | Δ μ-F1 [95% CI] | Δ m-F1 [95% CI] |
|---|---:|---:|---:|---:|---:|---|---|
| ECtHR A | 0.72 | 50.8% | 136 | 182 | 0.012 | +2.7 [+0.5, +4.8] | +9.5 [+5.8, +13.2] |
| ECtHR B | 0.72 | 43.7% | 109 | 246 | 3e-13 | −3.2 [−4.9, −1.4] | 0.0 [−3.5, +3.4] |
| SCOTUS | 0.57 | 64.1% | 249 | 174 | 3e-4 | +5.4 [+2.5, +8.1] | +1.4 [−4.0, +6.0] |
| EUR-LEX | 0.32 | 0.0% | 0 | 301 | 5e-91 | −32.5 [−33.1, −31.9] | −19.4 [−20.5, −18.2] |
| LEDGAR | 0.77 | 77.0% | 350 | 1615 | 1e-193 | −12.7 [−13.5, −11.8] | −19.1 [−20.5, −17.5] |
| UNFAIR-ToS | 0.42 | 75.1% | 31 | 348 | 5e-69 | −18.8 [−20.9, −16.7] | −25.7 [−30.8, −20.2] |
| CaseHOLD | 0.61 | 68.7% | 562 | 329 | 5e-15 | +6.5 [+4.8, +8.0] | +6.5 [+4.8, +8.0] |

Inter-model κ is pooled over label cells for multi-label tasks. "Same prediction" is an
identical label set.

Threshold-free ranking, macro ROC-AUC (`analysis/paired_auc.py` → `analysis/paired-auc.json`,
1000 paired resamples):

| Task | Jev | BERT | Δ [95% CI] |
|---|---:|---:|---|
| ECtHR A | 0.974 | 0.959 | +0.015 [+0.008, +0.022] |
| ECtHR B | 0.951 | 0.937 | +0.015 [+0.005, +0.026] |
| EUR-LEX | 0.902 | 0.947 | −0.045 [−0.048, −0.042] |
| UNFAIR-ToS | 0.992 | 0.977 | +0.015 [+0.006, +0.026] |

Findings:

- **Zero-shot Jev beats fine-tuned BERT on three tasks with paired significance:** CaseHOLD
  (+6.5 μ-F1), SCOTUS (+5.4 μ-F1), and ECtHR A (+2.7 μ-F1, +9.5 m-F1). It loses on LEDGAR,
  UNFAIR-ToS, EUR-LEX, and ECtHR B micro-F1.
- **On ECtHR A the F1 and McNemar results point in opposite directions.** Jev has higher
  F1 but fewer exactly correct label sets (136 vs 182, p=0.012), because over-predicted
  labels cost partial F1 credit but zero exact-match credit.
- **Jev ranks multi-label candidates better than BERT on ECtHR A/B and UNFAIR-ToS**
  (+0.015 AUC each, intervals above zero). There, the F1 deficit comes from Jev's
  uncalibrated 0.5 threshold (ECE 0.07 to 0.10 vs BERT's 0.005 to 0.034), not its ranking.
  EUR-LEX is the exception: BERT ranks better (−0.045 AUC) and wins on every metric.
- **The models make different mistakes.** Inter-model κ is 0.32 to 0.77. At least one model
  is right on 85.0% of SCOTUS cases (Jev 72.6%, BERT 67.2%), 86.4% of CaseHOLD
  (77.3% / 70.8%), and 91.5% of LEDGAR (75.3% / 88.0%). This is an upper bound on
  combining them, not a result; no ensemble was built or validated.
- **Single seed.** BERT's seed-to-seed spread is not measured here, so paired intervals
  cover test-sample variation only. Differences under about 1 F1 point (the gap between
  this seed and the published 5-seed means) should not be read as model differences.

## Third model: GPT-5.6 Luna (zero-shot, chat protocol)

- Model: `openai/gpt-5.6-luna`, run 2026-09-22, 23,607 / 23,607 scored, 0 failed
- Cost: $16.45 reported by OpenRouter (projection from n=50/task: $16.48); 41.5M input and
  5.5M output tokens. One 403 (key weekly limit) stopped the run at 92.3%; `--resume
  --retry-failed` completed it with 1,813 pending and 21,794 checkpointed (1 extra attempt).
- Protocol: `--protocol chat`, not System One. The System One endpoint rejects the model
  ("Model openai/gpt-5.6-luna does not exist"; it serves TypeSafe models only). Same
  instructions, label descriptions, 48,000-character truncation, and gold isolation, but the
  answer is JSON generated under a strict schema, and multi-label tasks return a label set:
  **no probabilities, no threshold, so no ROC-AUC or calibration for Luna.** Part of any
  Jev-Luna difference may come from the protocol rather than the model.

### F1, all three models

| Task | Luna μ-F1 [95% CI] | Jev μ-F1 | BERT μ-F1 | Luna m-F1 | Jev m-F1 | BERT m-F1 |
|---|---|---:|---:|---:|---:|---:|
| ECtHR A | **78.9** [76.9, 80.8] | 73.0 | 70.3 | **75.4** | 71.4 | 61.9 |
| ECtHR B | 78.8 [77.4, 80.1] | 75.4 | 78.6 | 73.3 | 72.6 | 72.5 |
| SCOTUS | 68.3 [65.9, 70.5] | **72.6** | 67.2 | 59.7 | 62.1 | 60.7 |
| EUR-LEX | 42.9 [42.4, 43.4] | 39.1 | **71.6** | 39.3 | 37.0 | **56.5** |
| LEDGAR | 74.7 [73.8, 75.5] | 75.3 | **88.0** | 62.2 | 63.3 | **82.4** |
| UNFAIR-ToS | 78.8 [76.9, 80.7] | 76.4 | **95.2** | 60.9 | 54.4 | **80.0** |
| CaseHOLD | 76.8 [75.5, 78.1] | 77.3 | 70.8 | 76.8 | 77.3 | 70.8 |
| Arithmetic mean | 71.3 | 69.9 | 77.4 | 63.9 | 62.6 | 69.3 |
| Harmonic mean | 68.4 | 66.3 | 76.3 | 61.1 | 59.3 | 68.0 |

BERT is the seed-1 reproduction above. Bold marks a best score separated from the others by
the paired tests below.

### Paired differences (1000-resample paired bootstrap, seed 0; McNemar on exact label sets)

Jev − Luna (`analysis/three-way.json`):

| Task | Δ μ-F1 [95% CI] | Δ m-F1 [95% CI] | Only Jev / only Luna exact | McNemar p | Inter-model κ |
|---|---|---|---:|---:|---:|
| ECtHR A | −5.9 [−7.4, −4.2] | −4.1 [−7.4, −0.5] | 68 / 204 | 6e-17 | 0.82 |
| ECtHR B | −3.4 [−4.5, −2.2] | −0.7 [−3.9, +3.2] | 84 / 159 | 2e-6 | 0.84 |
| SCOTUS | +4.3 [+2.4, +6.3] | +2.4 [−0.7, +5.4] | 133 / 73 | 4e-5 | 0.77 |
| EUR-LEX | −3.9 [−4.3, −3.4] | −2.3 [−2.9, −1.6] | 0 / 10 | 0.002 | 0.63 |
| LEDGAR | +0.7 [+0.1, +1.3] | +1.1 [+0.1, +2.1] | 508 / 441 | 0.03 | 0.86 |
| UNFAIR-ToS | −2.4 [−4.0, −0.8] | −6.6 [−10.1, −3.4] | 68 / 115 | 6e-4 | 0.78 |
| CaseHOLD | +0.5 [−0.9, +1.9] | +0.5 [−0.9, +1.9] | 315 / 296 | 0.47 | 0.74 |

Luna − BERT (`analysis/luna-vs-bert.json`):

| Task | Δ μ-F1 [95% CI] | Δ m-F1 [95% CI] | Only Luna / only BERT exact | McNemar p | Inter-model κ |
|---|---|---|---:|---:|---:|
| ECtHR A | +8.6 [+6.4, +10.8] | +13.6 [+9.7, +17.6] | 206 / 116 | 6e-7 | 0.73 |
| ECtHR B | +0.2 [−1.6, +1.9] | +0.7 [−3.9, +5.4] | 145 / 207 | 0.001 | 0.73 |
| SCOTUS | +1.1 [−1.9, +4.3] | −1.0 [−6.4, +3.4] | 251 / 236 | 0.53 | 0.52 |
| EUR-LEX | −28.6 [−29.3, −27.9] | −17.2 [−18.3, −15.9] | 5 / 296 | 1e-80 | 0.38 |
| LEDGAR | −13.3 [−14.2, −12.4] | −20.2 [−21.7, −18.6] | 356 / 1688 | 9e-207 | 0.76 |
| UNFAIR-ToS | −16.4 [−18.5, −14.3] | −19.1 [−24.3, −13.6] | 40 / 310 | 7e-53 | 0.46 |
| CaseHOLD | +5.9 [+4.1, +7.6] | +5.9 [+4.1, +7.6] | 599 / 385 | 9e-12 | 0.58 |

Agreement with gold, Luna: macro label κ ECtHR A 0.761 [0.704, 0.800], ECtHR B 0.705
[0.671, 0.732], EUR-LEX 0.370 [0.361, 0.377], UNFAIR-ToS 0.567 [0.520, 0.604]; Cohen's κ
SCOTUS 0.630 [0.602, 0.656], LEDGAR 0.741 [0.733, 0.750], CaseHOLD 0.710 [0.694, 0.726].

Findings:

- **The two zero-shot models are close, and neither dominates.** Luna leads on ECtHR A
  (+5.9 μ-F1), ECtHR B (+3.4), EUR-LEX (+3.9), and UNFAIR-ToS (+2.4). Jev leads on SCOTUS
  (+4.3) and marginally on LEDGAR (+0.7, lower CI bound +0.1). CaseHOLD is a tie. Arithmetic
  mean μ-F1 71.3 vs 69.9.
- **They agree with each other more than either agrees with BERT** (Jev-Luna κ 0.63 to 0.86
  vs 0.38 to 0.77 for either against BERT): the two zero-shot models make similar errors.
- **Luna over-predicts less on multi-label tasks** (ECtHR A 1.44 labels per document vs Jev
  1.58 and gold 1.09; EUR-LEX 5.97 vs 10.09 and gold 5.08), consistent with its gains there.
  Jev's multi-label answers pass through the fixed 0.5 threshold; Luna chooses a set directly.
- **Both zero-shot models trail fine-tuned BERT by 13 to 29 μ-F1 on EUR-LEX, LEDGAR, and
  UNFAIR-ToS,** the tasks with many or rare labels, and both beat it on CaseHOLD.
- **ECtHR B Luna vs BERT:** F1 ties (+0.2 [−1.6, +1.9]) but BERT gets more exact label sets
  (207 vs 145, p=0.001).
- The 350-example sample (50/task) run beforehand separated only ECtHR B; the full run
  separates five of seven Jev-Luna pairs. Sample result kept in
  `analysis/sample50-jev-vs-luna.json`.

## Jev with validation-tuned thresholds (multi-label tasks)

Jev's multi-label answers are per-label probabilities cut at 0.5. Thresholds were chosen on
the **validation** split and applied once to the stored test probabilities; test labels were
used only to score the frozen choice (`analysis/tune_threshold.py` →
`analysis/threshold-tuning.json`, rerun twice with identical output).

- Validation run: `typesafe/jev-1.13` (resolved `jev-1.13-20260917`, same as test), 9,275 /
  9,275 examples (ECtHR A/B 1,000 each, EUR-LEX 5,000, UNFAIR-ToS 2,275), $2.47. HTTP 529
  ("Overloaded") hit 39 times; the wrapper resumed each (fixed afterwards in `3490d86`).
- Rules fixed before scoring test: **primary**, one threshold per task maximizing validation
  micro-F1; **secondary**, one threshold per label maximizing that label's validation F1.
  Grid 0.05 to 0.95 by 0.05, ties to the value nearest 0.5. Labels with no positive
  validation example keep 0.5.
- This is allowed by the protocol (no test data, no training examples in prompts). It has no
  counterpart for Luna, whose chat answers carry no probabilities, or for BERT, which uses
  upstream's fixed 0.5.

| Task | Chosen (per task) | 0.5 μ / m | Per task μ / m | Per label μ / m | BERT μ / m |
|---|---:|---|---|---|---|
| ECtHR A | 0.65 | 73.0 / 71.3 | 74.0 / 70.6 | 74.3 / 73.8 | 70.3 / 61.9 |
| ECtHR B | 0.75 | 75.4 / 72.6 | 80.2 / 75.5 | 80.0 / 74.3 | 78.6 / 72.5 |
| EUR-LEX | 0.70 | 39.1 / 37.0 | 39.4 / 35.1 | 47.9 / 45.4 | 71.6 / 56.5 |
| UNFAIR-ToS | 0.90 | 76.4 / 54.4 | 90.6 / 35.2 | 91.9 / 67.9 | 95.2 / 80.0 |
| All 7 tasks, arithmetic mean | | 69.9 / 62.6 | 72.8 / 59.9 | **74.2 / 66.3** | 77.4 / 69.3 |
| All 7 tasks, harmonic mean | | 66.3 / 59.3 | 68.4 / 54.2 | 71.7 / 64.5 | 76.3 / 68.0 |

The means include the three single-label tasks unchanged. Paired bootstrap on test (1000
resamples, seed 0), Δ μ-F1 / Δ m-F1 with 95% CIs:

| Task | Per task − 0.5 | Per label − 0.5 | Per task − BERT | Per label − BERT |
|---|---|---|---|---|
| ECtHR A | +1.0 [−0.5, +2.7] / −0.8 [−4.5, +2.7] | +1.3 [−0.3, +3.2] / +2.5 [+0.6, +4.7] | +3.7 [+1.7, +6.0] / +8.7 [+4.2, +13.0] | +4.0 [+1.8, +6.4] / +12.0 [+8.3, +16.1] |
| ECtHR B | +4.8 [+3.5, +6.1] / +2.9 [+0.4, +5.7] | +4.6 [+3.1, +6.0] / +1.7 [−0.7, +4.6] | +1.6 [0.0, +3.2] / +2.9 [−0.4, +6.5] | +1.4 [−0.2, +3.1] / +1.7 [−1.5, +5.1] |
| EUR-LEX | +0.4 [0.0, +0.8] / −1.9 [−2.6, −1.3] | +8.9 [+8.5, +9.2] / +8.4 [+7.8, +9.0] | −32.1 [−32.8, −31.5] / −21.4 [−22.4, −20.1] | −23.6 [−24.2, −23.1] / −11.0 [−12.1, −9.8] |
| UNFAIR-ToS | +14.2 [+11.9, +16.5] / −19.1 [−25.2, −13.2] | +15.5 [+13.6, +17.4] / +13.6 [+9.0, +18.0] | −4.6 [−6.1, −3.2] / −44.8 [−50.8, −38.0] | −3.3 [−4.8, −1.9] / −12.1 [−17.9, −6.7] |

Findings:

- **The pre-registered primary (one threshold per task) helps micro-F1 but hurts macro-F1.**
  Mean μ-F1 69.9 → 72.8, mean m-F1 62.6 → 59.9. On UNFAIR-ToS a 0.9 cut gains 14.2 μ-F1
  and loses 19.1 m-F1: it suppresses rare categories along with false positives.
- **Per-label thresholds improve both** (mean 74.2 / 66.3), gaining on every multi-label task
  in μ-F1, most on UNFAIR-ToS (+15.5) and EUR-LEX (+8.9). With 8 to 100 thresholds fitted to
  1,000 to 5,000 validation documents they can overfit; the test gains are measured on held-out
  data, so overfitting would show up as smaller gains, not inflated ones.
- **Against BERT:** ECtHR B moves from −3.2 μ-F1 to +1.6 [0.0, +3.2] (per task), a
  borderline win; ECtHR A widens to +4.0. UNFAIR-ToS narrows from −18.8 to −3.3 μ-F1 but
  macro-F1 still trails by 12. **EUR-LEX remains far behind (−23.6 μ-F1)** even with
  per-label thresholds, consistent with its lower ranking quality (ROC-AUC 0.902 vs 0.947).
- With per-label thresholds Jev wins 4 of 7 tasks against fine-tuned BERT (ECtHR A, ECtHR B
  borderline, SCOTUS, CaseHOLD) and trails on 3 (EUR-LEX, LEDGAR, UNFAIR-ToS). The overall
  mean gap shrinks from 7.5 to 3.2 μ-F1 and from 6.7 to 3.0 m-F1.
- The Jev-vs-Luna and Jev-vs-BERT tables above use the 0.5 default and remain the zero-tuning
  comparison. Luna 71.3 / 63.9 falls between Jev at 0.5 and Jev with per-label thresholds.

## Corroboration outside law: intent detection (BANKING77, CLINC150)

Purpose: test the LEDGAR explanation (zero-shot errors cluster on fine-grained labels whose
boundaries are annotation conventions) on non-legal benchmarks with published fine-tuned
baselines. Jev only; baselines are the papers' numbers, so there is **no paired test**.

- Run: `typesafe/jev-1.13` (resolved `jev-1.13-20260917`), System One choice question over
  all intents, 8,580 / 8,580 test examples, 0 failures, 0 retries, $0.78 (projected $0.78
  from n=50/task).
- Data: BANKING77 from PolyAI-LDN/task-specific-datasets@57ec275 (SHA-256-checked CSVs; the
  Hub repo is only a loading script), 3,080 test queries, 40 per intent. CLINC150
  `clinc/clinc_oos@155b9c7`, config `plus` (the paper's OOS+), 4,500 in-scope + 1,000
  out-of-scope. Label descriptions are the intent codes with underscores as spaces; `oos` is
  "out of scope (the request fits none of the other intents)".
- Baselines, read from the papers' tables: BANKING77, Casanueva et al. (2020) Table 3,
  BERT-TUNED (BERT-large); CLINC150, Larson et al. (2019) Table 2, BERT, oos-train, OOS+.
  Neither reports intervals.

| Benchmark | Metric | Jev zero-shot [95% CI] | Fine-tuned BERT (published) |
|---|---|---|---:|
| BANKING77 | accuracy | 80.6 [79.3, 81.9] | 93.66 full; 90.03 at 30/intent; 83.42 at 10/intent |
| CLINC150 | in-scope accuracy | 89.0 [88.2, 89.9] | 96.7 |
| CLINC150 | out-of-scope recall | **88.1** [86.1, 90.1] | 59.2 (best in that column: Rasa, 66.0) |

Jev also: BANKING77 macro-F1 79.8, Cohen's κ 0.804, top-3 accuracy 91.4, ECE 0.089;
CLINC150 overall accuracy 88.9, κ 0.884, top-3 97.2, ECE 0.027, out-of-scope precision 81.9
(`analysis/intents-test.json`). The paper reports no out-of-scope precision, so the recall
gain cannot be priced against false out-of-scope calls on the BERT side.

Findings:

- **Same direction as LEDGAR.** Fine-grained single-domain intents trail fine-tuning by 13.0
  points (BANKING77), close to LEDGAR's 12.7; CLINC150's coarser multi-domain intents trail by
  7.7. Jev on BANKING77 falls below BERT trained on 10 examples per intent (−2.8).
- **The errors are label conventions again.** The largest BANKING77 confusion (30 of 596
  errors) is `get_physical_card` read as `change_pin`, on queries such as "I do not have my
  pin" and "How do I set-up my PIN for the new card?", which the annotators filed under
  getting a physical card. On CLINC150 the top pairs are `reminder_update`→`reminder` and
  `change_user_name`→`user_name`. The top 8 pairs account for 23% and 22% of errors.
- **Out-of-scope detection reverses the gap: +28.9 recall over BERT.** Recognizing that a
  request fits none of 150 intents takes judgment that 250 out-of-scope training queries do
  not teach well; the paper calls out-of-scope recall "much lower than in-scope across all
  methods". This parallels Jev's LexGLUE wins on CaseHOLD and SCOTUS. Cost: some in-scope
  queries go to out-of-scope (`change_accent` 20, `cancel` 17, `no` 16).
- Caveats: published baselines, not paired runs; BERT-large for BANKING77 vs our BERT-base
  reproduction for LexGLUE; both datasets are public since 2019 to 2020, so training-data
  overlap cannot be excluded.

## Kev's suites: Jev, Luna and Kev-4B on the Kev benchmark

[Kev](https://github.com/jaredpalmer/kev) is a family of open-weight decision models on
Qwen3.5/3.8 bases that serve TypeSafe's System One API. Its README scores Kev and Jev on two
frozen suites: `transfer-v4` ("new sources": QNLI, SciQ, PAWS, MMLU, Emotion,
TweetEval-offensive, held-out policy and rule items, none in Kev's training data) and
`decision-v7` ("trained sources": held-out items from Kev's ten training datasets, including
BANKING77, plus generated policies and rules).

- Runs 2026-09-27, all four splits (dev and locked test) of both suites, scored by Kev's own
  `kev.benchmark --remote` so metrics are computed exactly as Kev computes them. Suites and
  scorer from Kev commit `5920c5f`. Commands: `kev_suites/run_{jev,luna,kev}.sh`,
  `kev_suites/summarize.py`; output `analysis/kev-suites.{json,md}`.
- Jev: OpenRouter System One, `typesafe/jev-1.13` (served `jev-1.13-20260917`), 3,908 / 3,908
  records, 0 rejected.
- Luna: `openai/gpt-5.6-luna` behind `jev_test.chatshim`, a local System One endpoint that
  asks all of a record's questions in one strict-JSON chat call and returns one-hot answers.
  3,908 / 3,908 records, 0 rejected, 0 retries, $0.35. **One-hot answers, so accuracy only:**
  Luna's ECE, Brier and NLL are not meaningful and are not reported.
- Kev-4B: `jaredpalmer/kev-4b` (r10 release, bf16, temperature 2.41 applied by the server),
  served by Kev's own `kev_modal.py` at `5920c5f` on a Modal L40S. 3,908 / 3,908 records,
  0 rejected. The probabilities are temperature-scaled, as Kev ships them.
- BERT: not applicable. The LexGLUE baseline is one fine-tuned head per LexGLUE task; it has
  no head for these label sets.
- Harness checks:
  - Jev on `transfer-v4` dev: Kev published accuracy 0.857, ECE 0.049, Brier 0.211 (via
    Vercel AI Gateway); this run gives 0.855, 0.049, 0.211 via OpenRouter (1 of 656 answers
    differs).
  - Kev-4B: our served accuracy is within 0.004 of Kev's published fp32 numbers on every
    split (test: 0.838 vs 0.838, 0.866 vs 0.865), ECE within 0.005.
  - Serving code: the same four splits served at Kev `f2bb629` (8k-token context) and
    `5920c5f` (64k) differ by 0 to 4 argmax answers per split, accuracy by at most 0.0015,
    probabilities by at most 0.054. `5920c5f` is used because LexGLUE documents need the
    longer context (next section).

Intervals: 95% bootstrap over record groups (contrastive pairs resample together), 1000
resamples, seed 0, the same resamples for every quantity; differences are paired on identical
questions. n counts questions in Kev's "clean" variant.

| Split | n | Jev [95% CI] | Luna [95% CI] | Kev-4B [95% CI] | Jev − Luna [95% CI] | Jev − Kev-4B [95% CI] |
|---|---:|---|---|---|---|---|
| transfer-v4 dev | 656 | 0.855 [0.826, 0.883] | 0.881 [0.854, 0.907] | 0.814 [0.779, 0.845] | −0.026 [−0.051, −0.003] | +0.041 [0.012, 0.072] |
| transfer-v4 test | 656 | 0.877 [0.848, 0.901] | 0.898 [0.874, 0.920] | 0.838 [0.807, 0.867] | −0.021 [−0.043, −0.002] | +0.038 [0.012, 0.067] |
| decision-v7 dev | 1264 | 0.845 [0.823, 0.867] | 0.862 [0.840, 0.882] | 0.871 [0.849, 0.893] | −0.017 [−0.031, −0.001] | −0.026 [−0.046, −0.007] |
| decision-v7 test | 1200 | 0.835 [0.813, 0.856] | 0.846 [0.821, 0.867] | 0.866 [0.846, 0.888] | −0.011 [−0.028, 0.008] | −0.031 [−0.049, −0.011] |

| Split | Jev ECE / Brier / wrong at ≥ 0.9 | Kev-4B ECE / Brier / wrong at ≥ 0.9 | Kev-4B ECE before temperature (published) |
|---|---|---|---:|
| transfer-v4 dev | 0.049 / 0.211 / 0.037 | 0.037 / 0.243 / 0.009 | – |
| transfer-v4 test | 0.035 / 0.177 / 0.024 | 0.017 / 0.224 / 0.017 | 0.085 |
| decision-v7 dev | 0.062 / 0.237 / 0.053 | 0.013 / 0.182 / 0.016 | – |
| decision-v7 test | 0.056 / 0.246 / 0.041 | 0.019 / 0.186 / 0.008 | 0.080 |

Findings:

- **On new sources the order is Luna > Jev > Kev-4B.** Jev leads Kev-4B by 3.8 to 4.1 points
  with paired intervals above zero on both splits. Luna leads Jev by 2.1 to 2.6; on
  `transfer-v4` test the interval's upper end is −0.002 with this seed and 0.000 with others,
  so that split is borderline.
- **On Kev's training sources Kev-4B leads** Jev by 2.6 to 3.1 points (intervals below zero)
  and Luna by about 2. `decision-v7` is in-distribution for Kev and zero-shot for Jev and
  Luna, so this row measures what Kev's training buys, not a like-for-like comparison.
- **Kev-4B's served probabilities are better calibrated than Jev's** (test ECE 0.017 and 0.019
  vs 0.035 and 0.056; confident errors 0.8% to 1.7% vs 2.4% to 4.1%). That is Kev's
  temperature fit, made on its in-distribution development data: before it, Kev-4B's ECE was
  0.085 and 0.080, worse than Jev's raw 0.035 and 0.056. Jev has no fit here. Brier tracks
  accuracy more than calibration: Jev's Brier is lower on new sources, Kev-4B's on trained.
- **Per-source gaps are small-n (40 to 160).** Kev-4B's largest deficits to Jev on new sources
  are MMLU (0.700 vs 0.863, n=80), the composed-rule items (0.812 to 0.875 vs 0.906 to 1.000,
  n=32 each) and the deadline items (0.800 vs 0.900, n=40); its advantage is TweetEval
  offensive (0.850 vs 0.762). Jev's `return_window` items (0.600, n=40) trail both Luna
  (0.850) and Kev-4B (0.900). Full tables in `analysis/kev-suites.md`.
- Jev's BANKING77 accuracy here (0.738, n=80, Kev's option wording) is below its full-test
  80.6 [79.3, 81.9] from the section above. The 80-item sample's interval is about ±0.10, so
  this is not evidence of a difference. Kev-4B (0.850) was trained on BANKING77.

## Fourth model: Kev-4B on LexGLUE and the intent suite

- Model: `jaredpalmer/kev-4b` (r10, Qwen3.5-4B-Base + LoRA 16 + pointer head, bf16,
  temperature 2.41 applied by the server), served by Kev's `kev_modal.py` at Kev `5920c5f` on
  Modal L40S, run 2026-09-27. Same System One requests as Jev (`jev-bench run --endpoint
  <modal url> --model kev-latest`): same instructions, label descriptions, 48,000-character
  truncation, 0.5 multi-label threshold.
- LexGLUE test 23,607 / 23,607 and intents test 8,580 / 8,580, 0 failed, 0 retries. The
  intents job was killed at 1,530 and resumed (`jobs/kev4b-intents`); the ledger has 8,580
  unique ids.
- Cost: $8.01 Modal GPU for all Kev serving in this session (Kev suites, smoke test, both
  full runs); 73.3M input tokens on LexGLUE.
- Context: Kev's commit `f2bb629` serves states of at most 8,192 tokens and rejected a long
  ECtHR document with HTTP 422; `5920c5f` serves 64k. Kev-4B was trained on states of at most
  384 tokens (`MAX_STATE` in `kev/model.py`), so almost every LexGLUE document is longer than
  anything it trained on.

| Task | Kev-4B μ-F1 | Jev μ-F1 | Jev − Kev-4B Δ μ-F1 [95% CI] | Kev-4B m-F1 | Jev m-F1 | Δ m-F1 [95% CI] | Only Jev / only Kev exact | McNemar p |
|---|---:|---:|---|---:|---:|---|---:|---:|
| ECtHR A | 63.8 | 73.0 | +9.1 [+7.2, +11.0] | 60.5 | 71.4 | +10.9 [+7.7, +14.0] | 190 / 107 | 2e-6 |
| ECtHR B | 70.8 | 75.4 | +4.6 [+2.8, +6.3] | 65.4 | 72.6 | +7.2 [+4.1, +10.2] | 154 / 147 | 0.73 |
| SCOTUS | 59.3 | 72.6 | +13.3 [+10.9, +15.4] | 57.7 | 62.1 | +4.4 [+1.6, +7.1] | 230 / 44 | 1e-31 |
| EUR-LEX | 37.2 | 39.1 | +1.9 [+1.6, +2.2] | 36.0 | 37.0 | +1.1 [+0.5, +1.6] | 0 / 0 | 1 |
| LEDGAR | 68.0 | 75.3 | +7.3 [+6.6, +8.0] | 56.2 | 63.3 | +7.1 [+5.7, +8.3] | 1068 / 336 | 6e-89 |
| UNFAIR-ToS | 69.9 | 76.4 | +6.5 [+4.6, +8.5] | 47.3 | 54.4 | +7.1 [+3.9, +10.1] | 221 / 116 | 1e-8 |
| CaseHOLD | 65.5 | 77.3 | +11.8 [+10.4, +13.2] | 65.5 | 77.3 | +11.8 [+10.4, +13.3] | 618 / 193 | 1e-52 |
| Arithmetic mean | 62.1 | 69.9 | | 55.5 | 62.6 | | | |
| Harmonic mean | 59.4 | 66.3 | | 53.4 | 59.3 | | | |

Paired bootstrap, 1000 resamples, seed 0 (`analysis/jev-vs-kev4b.json`); ROC-AUC from
`analysis/paired-auc-kev4b.json`.

| Task | Kev-4B κ | Kev-4B ECE | Kev-4B mean conf. / accuracy | Jev ECE | Macro ROC-AUC Jev − Kev-4B [95% CI] |
|---|---:|---:|---|---:|---|
| ECtHR A | 0.587 | 0.095 | | 0.082 | +0.027 [+0.022, +0.034] |
| ECtHR B | 0.643 | 0.086 | | 0.096 | +0.014 [+0.009, +0.019] |
| SCOTUS | 0.536 | 0.080 | 0.555 / 0.593 | 0.148 | |
| EUR-LEX | 0.327 | 0.121 | | 0.099 | +0.011 [+0.009, +0.014] |
| LEDGAR | 0.674 | 0.244 | 0.436 / 0.680 | 0.116 | |
| UNFAIR-ToS | 0.418 | 0.157 | | 0.073 | +0.006 [+0.003, +0.009] |
| CaseHOLD | 0.569 | 0.053 | 0.602 / 0.655 | 0.038 | |

Intent detection (`analysis/intents-jev-vs-kev4b.json`):

| Benchmark | Kev-4B | Jev | Jev − Kev-4B [95% CI] | Kev-4B ECE / mean conf. |
|---|---:|---:|---|---|
| BANKING77 accuracy | 84.2 | 80.6 | −3.5 [−4.6, −2.3] | 0.146 / 0.696 |
| CLINC150 overall accuracy | 76.8 | 88.9 | +12.1 [+11.1, +13.2] | 0.322 / 0.446 |
| CLINC150 in-scope accuracy | 79.4 | 89.0 | | |
| CLINC150 out-of-scope recall / precision | 64.9 / 69.0 | 88.1 / 81.9 | | |

Findings:

- **Jev beats Kev-4B on all seven LexGLUE tasks,** μ-F1 by 1.9 to 13.3 points with every
  paired interval above zero; mean μ-F1 69.9 vs 62.1. The largest gaps are SCOTUS (+13.3) and
  CaseHOLD (+11.8), the smallest EUR-LEX (+1.9), where both are weak. Kev-4B's mean is below
  Luna (71.3) and fine-tuned BERT (77.4) as well. Jev also ranks multi-label candidates
  better (macro ROC-AUC +0.006 to +0.027, all intervals above zero), so the gap is not
  only a threshold effect.
- **Length is part of the explanation, not all of it.** Kev-4B trained on states of at most
  384 tokens; most LexGLUE documents are far longer. But CaseHOLD (no document truncated)
  shows the second-largest gap, and LEDGAR clauses (0 truncated) show +7.3, so
  short inputs do not close it. This run does not separate length from task difficulty.
- **Kev-4B is under-confident where Jev is over-confident.** Its mean confidence is below
  its accuracy on every single-label task, most on the largest label sets: LEDGAR (100
  labels) 0.44 at 0.68 accuracy, ECE 0.244; CLINC150 (151) 0.45 at 0.77, ECE 0.322; BANKING77
  (77) 0.70 at 0.84, ECE 0.146; SCOTUS (13) 0.56 at 0.59; CaseHOLD (5) 0.60 at 0.66. Jev's
  mean confidence exceeds its accuracy on SCOTUS and LEDGAR. Kev-4B's temperature (2.41) was
  fitted on Kev's own development data, and on Kev's suites it gives ECE 0.017 to 0.019
  (section above): the fit did not carry over to these tasks. Why it fails most on large
  label sets is not tested here.
- **BANKING77 is the one win for Kev-4B, and BANKING77 is one of Kev's training datasets**
  (`decision-v7`, held-out items from those datasets, includes it). It is not a zero-shot
  result. On CLINC150, which Kev did not train on, Jev leads by 12.1
  points and finds out-of-scope requests far better (recall 88.1 vs 64.9).
- **The two models disagree less than the F1 gap suggests** (inter-model κ 0.62 to 0.79 on
  LexGLUE): where one is right the other usually is too, and the gap comes from the cases
  only Jev gets right (e.g. LEDGAR 1,068 vs 336, CaseHOLD 618 vs 193).
- Single run, one checkpoint, one serving configuration (bf16 on L40S). Kev-4B's served
  accuracy on Kev's own suites matched its published fp32 numbers within 0.004, so the
  serving path is not a likely cause of the LexGLUE gap.

## A fine-tuned encoder on Kev's training data: ModernBERT-large

Question: does a small BERT-like model trained on the same data as Kev-4B match it on Kev's
suites? Kev-4B is a 4B decoder with a LoRA adapter and pointer head, trained on Kev's
`decision-v7` train partition. This trains a 396M encoder on exactly that partition.

- Model: `answerdotai/ModernBERT-large` (rev `45bb465`, 8,192-token context), as a
  cross-encoder: each option of a question becomes one (input, question + option) pair, a
  scalar head scores each pair, and a softmax over the question's pairs gives its answer.
  This handles Kev's per-question option sets (2 to 78 options, yes/no, graded levels),
  which a fixed label head cannot. Code: `encoder/crossenc.py` (framing, checked against
  Kev's own `api_request` on all 17,452 records: 0 mismatches), `encoder/modal_app.py`.
- Data: `decision-v7` train, 12,576 records / 15,576 questions (sha256 `7ed5254b…`, as in
  Kev's manifest), fetched by Kev's `load_split` from `jaredpalmer/kev-suites@a88f56d`.
- Training: 2 epochs (Kev's count), AdamW lr 2e-5, linear schedule with 6% warmup, batches
  of at most 128 pairs, bf16, one seed, H100 on Modal, 936 s. Checkpoint selected on
  `decision-v7` development accuracy (best 0.826 at step 2,400 of 2,484, still rising).
  Temperature 1.62 fitted on `decision-v7` calibration (NLL 0.463 → 0.429), as Kev fits its
  own. The run was interrupted at step ~600 and resumed from its step-600 checkpoint
  (learning-rate schedule continuous across the restart).
- Control: `MoritzLaurer/ModernBERT-large-zeroshot-v2.0` (rev `a51e07b`), the same backbone
  trained for NLI, scored zero-shot with the same pairs (entailment minus not-entailment
  logit), temperature fitted the same way. The NLI model expects a declarative hypothesis;
  the question-plus-option text is not one (it scores 0.375 on the MNLI items it was built
  for), so this is a floor for zero-shot NLI, not its best case.
- Scoring: logits for every record are computed once on Modal; `encoder/replay.py` serves
  them as a System One endpoint so Kev's own `kev.benchmark` scores them
  (`kev_suites/run_encoder.sh`). 3,908 / 3,908 records per model, 0 rejected.
- Cost: $2.15 Modal GPU for the bench, training (including the interrupted segment and
  three failed resumes before a fix), and both prediction runs.

Accuracy, 95% bootstrap over record groups, 1000 resamples, seed 0 (`analysis/kev-suites.md`):

| Split | n | Jev | Luna | Kev-4B | ModernBERT fine-tuned | ModernBERT NLI zero-shot |
|---|---:|---|---|---|---|---|
| transfer-v4 dev | 656 | 0.855 [0.826, 0.883] | 0.881 [0.854, 0.907] | 0.814 [0.779, 0.845] | 0.572 [0.533, 0.607] | 0.537 [0.499, 0.572] |
| transfer-v4 test | 656 | 0.877 [0.848, 0.901] | 0.898 [0.874, 0.920] | 0.838 [0.807, 0.867] | 0.604 [0.566, 0.642] | 0.575 [0.538, 0.610] |
| decision-v7 dev | 1264 | 0.845 [0.823, 0.867] | 0.862 [0.840, 0.882] | 0.871 [0.849, 0.893] | 0.801 [0.774, 0.825] | 0.627 [0.598, 0.657] |
| decision-v7 test | 1200 | 0.835 [0.813, 0.856] | 0.846 [0.821, 0.867] | 0.866 [0.846, 0.888] | 0.798 [0.773, 0.822] | 0.631 [0.602, 0.660] |

| Split | Kev-4B − ModernBERT ft [95% CI] | Jev − ModernBERT ft [95% CI] | ModernBERT ft ECE / Brier |
|---|---|---|---|
| transfer-v4 test | +0.235 [+0.195, +0.277] | +0.273 [+0.233, +0.313] | 0.094 / 0.522 |
| decision-v7 test | +0.068 [+0.045, +0.091] | +0.037 [+0.014, +0.061] | 0.060 / 0.296 |

Findings:

- **Trained on the same data, the encoder trails Kev-4B by 6.8 points on Kev's training
  sources and by 23.5 on the held-out ones.** Kev-4B loses 2.8 points going from trained to
  held-out sources (test 0.866 → 0.838); the encoder loses 19.4 (0.798 → 0.604), ending 2.9
  points above the untrained NLI control on held-out sources.
- **What does not transfer is rule application and knowledge.** On held-out test sources the
  encoder is near chance on the new policy and rule families (composed rules 0.53 to 0.59 on
  two options, n=32 each; deadline levels 0.325 on three, n=40; authorization 0.55, answering
  "true" 38 of 40 times), on MMLU (0.338, chance 0.25, n=80) and on PAWS (0.562, "true" 76
  of 80). It holds up where the held-out task resembles training (QNLI 0.825, SciQ 0.850,
  TweetEval-offensive 0.787, n=80 each). On the policy families it trained on, it scores
  0.775 to 1.000 (n=40 each): it learned those families, not how to apply a stated rule.
- **On trained sources the gap is smaller but real.** The encoder trails Kev-4B most on
  DBpedia (0.863 vs 1.000), BoolQ (0.762 vs 0.875), BANKING77 (0.713 vs 0.850) and MNLI
  (0.800 vs 0.925), n=80 each, and is ahead on Yelp yes/no (0.925 vs 0.912), Amazon (0.600
  vs 0.588) and the quantity-limit policy items (0.975 vs 0.900, n=40), all within one or
  two answers at these sample sizes except the last.
- **Calibration after the same kind of temperature fit is worse than Kev-4B's** (test ECE
  0.094 and 0.060 vs 0.017 and 0.019).
- Limits: one seed, one learning rate, 2 epochs with dev accuracy still rising at the end,
  and pairs truncated to 512 tokens (Kev's suites admit states of at most 384 Qwen tokens,
  so truncation should be rare, but it was not counted). A longer or tuned run could narrow
  the trained-source gap; the held-out gap is 3.5x the trained-source one, which a few
  points of tuning would not close.

## Fifth model: LLM2Jev, a prompted Qwen3.5-4B behind the System One API

[LLM2Jev](https://github.com/Yinsongxu/LLM2Jev) (Apache-2.0, commit `a4aafa8`) turns a stock
chat model into a System One server with no training. Every candidate of every question becomes
one yes/no chat prompt ("Is this candidate "X" the best answer?"); the server reads P(yes) from
the next-token logits of a zero-token SGLang prefill. Choice candidates are L1-normalized; a
noul with true/false criteria (our multi-label requests) is scored as two candidates and
normalized the same way. Its README reports 76.2% on the 231 public JevBench items with
Qwen3.5-4B. That base matters here: Kev-4B is Qwen3.5-4B-Base plus a trained LoRA and pointer
head, so LLM2Jev vs Kev-4B compares prompting an instruct model with training on Kev's data at
the same size and family.

- Serving: LLM2Jev's own `llm2jev-serve --backend sglang` (staged submission, its default) on
  `lmsysorg/sglang:v0.5.20-cu130` (the SGLang version its lockfile pins), `Qwen/Qwen3.5-4B` at
  revision `851bf6e`, bf16, served name `qwen3.5-4b`, H100 on Modal, at most two containers.
  Code: `llm2jev_bench/modal_app.py`. Runs 2026-09-28/29.
- Same requests as Jev: `jev-bench run --endpoint <modal url> --model qwen3.5-4b` (same
  instructions, label descriptions, 48,000-character truncation, 0.5 multi-label threshold);
  Kev's suites through `kev.benchmark --remote` (`kev_suites/run_llm2jev.sh`).
- Coverage: LexGLUE test 23,607 / 23,607, intents test 8,580 / 8,580, Kev's suites 3,908 /
  3,908 records (0 rejected). Every response reports `qwen3.5-4b`.
- Cost: $28.84 Modal GPU for everything below (Modal billing report, app `jev-test-llm2jev`),
  including the checks, the smoke run and idle scale-down time. LLM2Jev counted 3.11B prompt
  tokens on LexGLUE, most of them served from the prefix cache.
- Incidents, none of which lost or duplicated a result (each ledger has one successful record
  per id): (1) Modal disabled the workspace mid-run (HTTP 404, "workspace is disabled", from
  22:36 until re-enabled by 23:10 local); the runners stopped and resumed from their checkpoints. (2) SGLang 0.5.20's
  scheduler died three times at container start: it gives a request without
  `token_ids_logprob` a list placeholder and then calls `.tolist()` on it, and its own startup
  warmup `/generate` request shares a batch with the first scoring requests. Fixed with
  `--skip-server-warmup` (a 64-request burst on cold containers then returned 64 × HTTP 200);
  `--disable-overlap-schedule`, an earlier partial workaround, stayed on for every result. 52
  LexGLUE and 32 intent requests failed during these incidents and were re-sent on resume.

Checks before the full runs:

- **Serving matches LLM2Jev's published number.** JevBench (`fstandhartinger/jevbench@9ec6f15`,
  typesafe adapter, the 231 public items) through our endpoint: 177 / 231 = 76.6% (±5.5 at
  95%), against LLM2Jev's 76.2% (176 / 231). `results/llm2jev/jevbench/`. Latency there (P50
  0.55 s) includes the internet round trip to Modal and is not comparable to LLM2Jev's local
  48 ms.
- **Prefix reuse does not change answers.** Qwen3.5 is a hybrid (Gated DeltaNet) model, and
  LLM2Jev's speed comes from SGLang reusing each document's prefix across candidates. On 27 real
  requests (3 per task from the LexGLUE and intent smoke sets, 1,422 probabilities), the served
  config against one with no prefix cache and all candidates submitted at once: mean |Δp|
  0.0018, max 0.033, 1 of 399 decisions differs; 694k vs 2.09M prefilled tokens, 14.8 s vs 32.6 s
  serially. `llm2jev_bench/compare_configs.py`, `results/llm2jev/prefix-check.json`.
- **Resume**: a 350-document smoke run killed at 152 and relaunched finished with 350 unique
  ids and no duplicates.

### LexGLUE

Paired bootstrap, 1000 resamples, seed 0 (`analysis/jev-vs-llm2jev.json`,
`analysis/kev4b-vs-llm2jev.json`); ROC-AUC from `analysis/paired-auc-llm2jev.json` and
`analysis/paired-auc-kev4b-vs-llm2jev.json`.

| Task | LLM2Jev μ-F1 [95% CI] | Kev-4B | Jev | Jev − LLM2Jev Δ μ-F1 [95% CI] | Kev-4B − LLM2Jev Δ μ-F1 [95% CI] | LLM2Jev m-F1 | Only Kev / only LLM2Jev exact |
|---|---|---:|---:|---|---|---:|---:|
| ECtHR A | 53.8 [52.1, 55.6] | 63.8 | 73.0 | +19.2 [+17.6, +20.8] | +10.1 [+8.0, +12.0] | 49.6 | 258 / 62 |
| ECtHR B | 61.3 [60.0, 62.8] | 70.8 | 75.4 | +14.1 [+12.8, +15.4] | +9.4 [+7.7, +11.2] | 56.8 | 253 / 61 |
| SCOTUS | 71.6 [69.3, 74.1] | 59.3 | 72.6 | +0.9 [−0.6, +2.3] | −12.4 [−14.5, −10.1] | 63.4 | 54 / 227 |
| EUR-LEX | 37.1 [36.7, 37.4] | 37.2 | 39.1 | +2.0 [+1.8, +2.3] | +0.1 [−0.1, +0.4] | 33.5 | 0 / 0 |
| LEDGAR | 71.3 [70.3, 72.1] | 68.0 | 75.3 | +4.0 [+3.4, +4.7] | −3.3 [−4.0, −2.6] | 57.9 | 569 / 896 |
| UNFAIR-ToS | 74.3 [72.2, 76.4] | 69.9 | 76.4 | +2.1 [+0.5, +3.7] | −4.3 [−6.1, −2.4] | 49.8 | 112 / 188 |
| CaseHOLD | 65.9 [64.2, 67.3] | 65.5 | 77.3 | +11.4 [+9.9, +12.9] | −0.4 [−1.8, +1.1] | 65.9 | 380 / 394 |
| Arithmetic mean | 62.2 | 62.1 | 69.9 | | | 53.8 | |
| Harmonic mean | 59.1 | 59.4 | 66.3 | | | 51.5 | |

| Task | LLM2Jev ECE | LLM2Jev mean conf. / accuracy | Pred. / gold labels per doc (LLM2Jev, Kev-4B) | Macro ROC-AUC Jev − LLM2Jev [95% CI] | Kev-4B − LLM2Jev [95% CI] |
|---|---:|---|---|---|---|
| ECtHR A | 0.286 | | 2.53, 1.34 / 1.09 | +0.035 [+0.030, +0.041] | +0.008 [+0.002, +0.015] |
| ECtHR B | 0.275 | | 2.85, 1.65 / 1.44 | +0.029 [+0.023, +0.036] | +0.015 [+0.008, +0.022] |
| SCOTUS | 0.513 | 0.203 / 0.716 | | | |
| EUR-LEX | 0.195 | | 9.88, 11.60 / 5.08 | +0.031 [+0.028, +0.034] | +0.020 [+0.016, +0.023] |
| LEDGAR | 0.627 | 0.086 / 0.713 | | | |
| UNFAIR-ToS | 0.169 | | 0.41, 0.45 / 0.12 | +0.003 [+0.001, +0.005] | −0.003 [−0.006, −0.000] |
| CaseHOLD | 0.307 | 0.352 / 0.659 | | | |

### Intent detection

`analysis/intents-jev-vs-llm2jev.json`, `analysis/intents-kev4b-vs-llm2jev.json`:

| Benchmark | LLM2Jev [95% CI] | Kev-4B | Jev | Jev − LLM2Jev [95% CI] | Kev-4B − LLM2Jev [95% CI] | LLM2Jev ECE / mean conf. |
|---|---|---:|---:|---|---|---|
| BANKING77 accuracy | 67.3 [65.8, 68.9] | 84.2 | 80.6 | +13.3 [+11.8, +14.7] | +16.9 [+15.1, +18.4] | 0.577 / 0.096 |
| CLINC150 overall accuracy | 73.3 [72.2, 74.6] | 76.8 | 88.9 | +15.5 [+14.4, +16.6] | +3.4 [+2.2, +4.6] | 0.667 / 0.066 |
| CLINC150 in-scope accuracy | 75.8 [74.6, 77.1] | 79.4 | 89.0 | | | |
| CLINC150 out-of-scope recall / precision | 62.1 / 80.9 | 64.9 / 69.0 | 88.1 / 81.9 | | | |

LLM2Jev top-3 accuracy: BANKING77 84.2, CLINC150 88.8.

### Kev's suites

Accuracy, 95% bootstrap over record groups, 1000 resamples, seed 0 (`analysis/kev-suites.md`;
adding LLM2Jev left every earlier entry of `analysis/kev-suites.json` byte-identical):

| Split | n | LLM2Jev | Kev-4B | Jev | Jev − LLM2Jev [95% CI] | Kev-4B − LLM2Jev [95% CI] | LLM2Jev ECE / mean conf. |
|---|---:|---|---:|---:|---|---|---|
| transfer-v4 dev | 656 | 0.730 [0.691, 0.767] | 0.814 | 0.855 | +0.125 [+0.090, +0.161] | +0.084 [+0.049, +0.119] | 0.094 / – |
| transfer-v4 test | 656 | 0.765 [0.732, 0.799] | 0.838 | 0.877 | +0.111 [+0.077, +0.144] | +0.073 [+0.039, +0.110] | 0.117 / 0.649 |
| decision-v7 dev | 1264 | 0.773 [0.747, 0.799] | 0.871 | 0.845 | +0.072 [+0.049, +0.093] | +0.098 [+0.077, +0.122] | 0.153 / – |
| decision-v7 test | 1200 | 0.759 [0.736, 0.783] | 0.866 | 0.835 | +0.076 [+0.053, +0.101] | +0.107 [+0.083, +0.131] | 0.137 / 0.626 |

Findings:

- **Trained beats prompted at the same size on Kev's suites.** Kev-4B leads LLM2Jev by 7.3 to
  10.7 points on all four splits, intervals above zero, and on held-out sources (7.3 to 8.4) as
  well as on its own training sources (9.8 to 10.7). Against the ModernBERT cross-encoder
  trained on Kev's data, LLM2Jev is ahead on held-out sources (test 0.765 vs 0.604) and behind on
  the trained ones (0.759 vs 0.798).
- **The gap is in rule application.** On held-out test items LLM2Jev scores 0.500 on
  composed rules with an exception and 0.562 with a negation (two options, n=32 each; Kev-4B
  0.875 and 0.906) and 0.475 on deadline items (three options, n=40; Kev-4B 0.800). On the
  quantity-limit policy items it answers "held for review" for all 40 test items, whatever the
  quantity (0.300; Kev-4B 0.900), and 0.250 on the 24 dev items. It matches Kev-4B on the
  standard datasets (QNLI 0.887 vs 0.900, PAWS 0.825 vs 0.825, SciQ 1.000 vs 1.000, n=80 each).
- **On LexGLUE the mean ties Kev-4B (62.2 vs 62.1 μ-F1) with opposite task profiles.** LLM2Jev
  leads on SCOTUS (+12.4), UNFAIR-ToS (+4.3) and LEDGAR (+3.3) and trails on ECtHR A and B
  (−10.1, −9.4); EUR-LEX and CaseHOLD are ties. Kev-4B trained on states of at most 384 tokens,
  and LLM2Jev uses the instruct model's native context, so length is a candidate explanation
  for SCOTUS (613 of 1,400 documents truncated at 48,000 characters); this run does not test
  it. Jev leads LLM2Jev on the mean by 7.7 μ-F1 (69.9 vs 62.2) and on six of seven tasks, most
  on ECtHR A (+19.2) and CaseHOLD (+11.4); SCOTUS is a tie (+0.9 [−0.6, +2.3]). Jev also ranks
  multi-label candidates better on all four tasks (ROC-AUC +0.003 to +0.035).
- **ECtHR errors are over-prediction at the 0.5 cut-off.** LLM2Jev predicts 2.5 and 2.8
  articles per case where gold has 1.1 and 1.4 (precision 0.40 and 0.46 at recall 0.92). The
  test-set oracle threshold (0.55, diagnostic only) would lift ECtHR A to 58.0, still below
  Kev-4B's 63.8.
- **Choice probabilities are uninformative as confidences on large label sets.** Normalizing
  independent yes-probabilities spreads the mass across every plausible candidate: mean
  confidence 0.086 at 0.713 accuracy on LEDGAR (100 labels), 0.066 at 0.733 on CLINC150 (151),
  0.203 at 0.716 on SCOTUS (13), ECE 0.51 to 0.67. The ranking holds (top-3 accuracy 84 to 89%),
  so the argmax is usable and the probabilities are not. On Kev's suites (2 to 5 options for
  most questions) the same under-confidence is milder: mean confidence 0.63 to 0.65 at 0.76 to
  0.77 accuracy. No temperature or calibration fit was applied, as LLM2Jev ships none.
- **Exact 0.5 ties are rare.** A multi-label noul lands on exactly 0.5 when the model says yes
  (or no) to both the true and the false candidate with probability ~1; the strict `> 0.5` rule
  reads that as "does not apply". 2,599 of 532,856 label decisions (0.12% to 1.1% per task),
  264 of them gold-positive (`analysis/llm2jev-ties.json`).
- **Intents: LLM2Jev trails both models.** On CLINC150, which is not in Kev's training data,
  Jev leads by 15.5 and Kev-4B by 3.4, and LLM2Jev's out-of-scope recall is 62.1 vs Jev's 88.1.
  BANKING77 is in Kev-4B's training data, so its +16.9 there is not zero-shot.
- **The JevBench ranking does not carry over.** LLM2Jev's comparison table
  (`docs/jevbench.md`, kev 4B from JevBench's published v1.2 results) puts LLM2Jev (76.2%) above
  kev 4B (66.2%) on the 231 public items; on Kev's 3,908 records Kev-4B leads by 7 to 11 points,
  and on LexGLUE they tie. The 231-item accuracy has an interval of about ±5.5 points, and the
  kev 4B figure there is JevBench's measurement, not ours.
- Limits: one base model (the one LLM2Jev published), one prompt (LLM2Jev's default), one run;
  multi-label requests always carry true/false criteria, so LLM2Jev's single-candidate noul
  path (raw P(yes), no normalization) was not tested; bf16 serving numerics shift a few
  decisions (1 in 399 between cache configs).

## External cross-check: Decision Index v0.2.1 and Cloudflare's Clef

Cloudflare's [Clef post](https://blog.cloudflare.com/clef-decision-models/) (2026-10-01)
releases two System One-compatible decision models: Clef (frozen Qwen3.8-27B, a joint schema
head and rank-256 LoRA) and Clef-flash (Qwen3.5-9B), trained on "internal synthetic datasets"
with label-smoothed cross-entropy, a Brier loss and an RL objective. Its benchmark table is the
community [Decision Index](https://huggingface.co/spaces/multimodalart/jev-decision-index)
v0.2.1 suite, which includes our intent suite on the same test sets (BANKING77 3,080,
CLINC150+OOS 5,500), scored by macro-F1.

- Provenance (checked against `data/index-v0.2.1.json`, Space revision `cdbd1ca`, built
  2026-09-28): the post's Jev, DiffusionGemma Jev, Kev 9B and Laya columns equal the index
  values. The Clef columns come from Cloudflare's "internal run of the Decision Index 0.2.1
  suite" (model card); Clef is not among the index's 70 entrants. Not reproduced here.
- Our side: `analysis/decision_index_check.py` → `analysis/decision-index-check.json`, macro-F1
  from the ledgers in the intent section above, 1000-resample bootstrap, seed 0.

| Benchmark (macro-F1) | Jev ours [95% CI] | Jev index | Kev-4B ours [95% CI] | Kev-4B index | Kev 9B index | LLM2Jev ours | Clef (Cloudflare) | Clef-flash (Cloudflare) |
|---|---|---:|---|---:|---:|---:|---:|---:|
| BANKING77 | 79.8 [78.4, 80.9] | 79.7 | 83.8 [82.3, 84.8] | 82.2 | 84.8 | 67.5 | 94.2 | 90.9 |
| CLINC150+OOS | 89.1 [88.3, 89.8] | 89.3 | 79.4 [78.1, 80.1] | 79.4 | 79.0 | 73.8 | 97.4 | 66.8 |

Findings:

- **Our Jev intent numbers reproduce on an independent harness**: +0.10 and −0.13 points from
  the index, inside our intervals, from a separate harness and client. Kev-4B matches on
  CLINC150 (−0.01); on BANKING77 ours is 1.6 points higher, just outside our interval. The
  items are identical, so that gap is prompt wording or serving, not sampling; not tested.
- **Clef's intent scores would close the gap to fine-tuning reported above.** BANKING77 94.2
  macro-F1 sits beside fine-tuned BERT-large's 93.66 accuracy, CLINC150+OOS 97.4 beside BERT's
  96.7 in-scope accuracy (different metrics; a rough comparison only). Cloudflare does not list
  its training sources. Training on a benchmark's source lifts it: Kev-4B, trained on BANKING77,
  leads Jev there by 3.5 accuracy points and trails by 12.1 on CLINC150, and Kev 9B's model card
  lists `banking77` among its datasets. Whether Clef saw these sets is unknown, so its scores
  are not evidence of zero-shot intent skill until that is ruled out.
- **Clef-flash's CLINC150+OOS score (66.8) is 30.7 points below Clef's**, against a 3.3-point
  gap on BANKING77. Neither the post nor the card explains it; out-of-scope handling is a
  candidate, since that is where CLINC150 differs from BANKING77. Not tested without
  per-item outputs.
- **Across the card's 41 benchmarks, Clef beats Jev on 26 and trails on 15** (median +2.7
  points; Clef-flash 24 / 16 / 1 tie, median +1.1). The post's 10-row table shows two of the
  losses. The largest deficits are reasoning and knowledge: GPQA Diamond −30.3, BBH −19.2,
  MMLU-Pro −16.8.
- **The latency comparison with Jev is not like-for-like.** The post sets Clef's 209 ms median
  against Jev's 524 ms. The index labels Jev's figure "Hosted API, network round-trip from our
  lab ... Not comparable to the on-card single-process figures" (`methodology-v0.2.1.json`).
  The post gives no hardware or protocol for Clef's timing.
- **No calibration numbers.** Clef trains with a Brier loss, but neither the post nor the card
  reports ECE or Brier. Jev's ECE on these sets is 0.089 (BANKING77) and 0.027 (CLINC150).
