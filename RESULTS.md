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
