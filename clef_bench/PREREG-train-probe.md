# Pre-registration: did Clef-flash train on BANKING77 and CLINC150?

Written 2026-10-02, after the Clef-flash intent test run and before any training-split request.

## Observation that prompted it

Clef-flash on the full test splits, our System One requests (same as Jev's), served from
`Cloudflare/clef-flash@17f0b0a`:

- BANKING77 macro-F1 95.8 [95.1, 96.4] (n=3,080). Published fine-tuned BERT-large: 93.66
  accuracy. Cloudflare's own reported Clef-flash number: 90.93.
- CLINC150+OOS macro-F1 98.6 [98.2, 98.8] (n=5,500). Published fine-tuned BERT: 96.7
  in-scope accuracy. Cloudflare's reported Clef-flash number: 66.77.

A zero-shot model above full-data fine-tuning on BANKING77, whose errors for Jev are mostly
annotation conventions, suggests Clef-flash saw these datasets in training. Cloudflare lists
its training data only as "internal synthetic datasets".

## Probe

Score a random sample of each dataset's **training** split (1,000 queries per dataset,
`jev-bench prepare --split train --limit 1000 --seed 42`) with the same requests, and compare
accuracy with the test split.

- A model fine-tuned on a training split scores higher on those items than on held-out test
  items. A model that never saw the dataset scores the same on both, within sampling error,
  since the splits share one distribution.
- Control: Jev (`typesafe/jev-1.13`) on the same training samples, to absorb any difficulty
  difference between the splits.

## Prediction

Clef-flash's train accuracy exceeds its test accuracy by at least 2 points on BANKING77
(test accuracy is about 95.8, so train at 98 or above) and by a smaller margin on CLINC150,
whose test accuracy is already near 98.5. Jev's train − test difference is within ±1.5
points with an interval covering zero.

## Decision rule

Accuracy, 95% bootstrap intervals (1000 resamples, seed 0), resampling train and test items
independently.

- **Exposure indicated** for a dataset if Clef-flash's (train − test) interval excludes zero
  and the difference-in-differences (Clef-flash gap − Jev gap) interval also excludes zero.
- **No evidence of exposure** if Clef-flash's (train − test) interval covers zero. This does
  not show the model never saw the data: training on both splits, or with strong
  regularization, would leave no gap.
- If Jev's own gap excludes zero, the splits differ in difficulty and only the
  difference-in-differences is read.

Whatever the outcome, the result goes into RESULTS.md with this file's prediction.
