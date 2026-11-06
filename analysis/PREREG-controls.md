# Pre-registration: context, prompt and redraw controls (2026-11-05)

Written before any full control run was sent. The only API calls made before this file were
10-document cost smokes per task (`results/*-smoke`), which are not scored here.

## Why

The 2026-11-05 audit raised three confounds that no existing run separates:

1. **Context length.** Jev reads up to 48,000 characters; fine-tuned BERT reads what upstream
   LexGLUE feeds it (ECtHR, SCOTUS: 64 segments × 128 tokens; EUR-LEX: 512 tokens). Jev leads
   BERT on ECtHR A (+2.7 [+0.5, +4.8] μ-F1) and SCOTUS (+5.4 [+2.5, +8.1]).
2. **Prompt.** `--protocol chat` asks multi-label tasks as one "select every option that
   applies" question; System One asks one yes/no question per label with criterion sentences.
   Luna leads Jev on four multi-label tasks: ECtHR A (Jev − Luna −5.9 [−7.4, −4.2]), ECtHR B
   (−3.4 [−4.5, −2.2]), EUR-LEX (−3.9 [−4.3, −3.4]), UNFAIR-ToS (−2.4 [−4.0, −0.8]).
3. **Single draw.** Every model was scored once; bootstrap intervals cover test-set
   resampling, not run-to-run variation. A 10-document smoke found Jev returns different
   probabilities for byte-identical requests (32 of 37 differed, by up to 0.05).

## Arms (all on identical ids within a task)

| Arm | Run dir | Data | Model / protocol |
|---|---|---|---|
| J0 | `results/full-test` (existing) | full-test | Jev, System One, 48,000 chars |
| J1 | `results/jev-redraw` | `data/control-full` | J0 repeated (redraw) |
| JB | `results/jev-bertctx` | `data/control-bertctx` | Jev, System One, text cut to BERT's input (`bert/context_matched.py`), `--max-chars 0` |
| L0 | `results/luna-full` (existing) | full-test | Luna, `chat` |
| L1 | `results/luna-redraw` | `data/multilabel-control` | L0 repeated (redraw) |
| LP | `results/luna-perlabel` | `data/multilabel-control` | Luna, `chat-perlabel` |

Tasks: J1 on ECtHR A, ECtHR B, SCOTUS, UNFAIR-ToS, EUR-LEX (500-document sample, seed 42);
JB on the same minus UNFAIR-ToS (BERT's 128-token cut keeps 98.4% of its characters; LEDGAR
and CaseHOLD keep 98.2% and 98.5%, so they are not run); L1 and LP on ECtHR A, ECtHR B,
UNFAIR-ToS and the same EUR-LEX sample. Budget: about $10.4 of $15.95 OpenRouter credit.

All comparisons: paired bootstrap of micro-F1 (and macro-F1) differences,
`jev_test.analysis.paired`, 1,000 resamples, seed 0, ids sorted.

## Predictions

- **P1 (redraw noise).** J1 − J0 and L1 − L0 are within ±1.0 μ-F1 on every task, and every
  interval includes zero.
- **P2 (context).** JB − J1 is negative on SCOTUS (BERT's input keeps 32% of the characters),
  between −1 and −5 points; on ECtHR A/B (71% kept) between 0 and −2; on EUR-LEX (19% kept)
  between −1 and −4.
- **P3 (prompt).** LP − L1 is within ±3 μ-F1 on each task, sign not predicted; per-label
  questions raise Luna's mean predicted labels per document (recall up, precision down).

## Decision rules

- **R1.** A redraw interval that excludes zero, or |J1 − J0| or |L1 − L0| above 1.0, means
  single-draw results understate uncertainty on that task; RESULTS.md then states the redraw
  difference next to every single-draw comparison on that task.
- **R2.** Jev's lead over BERT on ECtHR A or SCOTUS is attributed to context if JB − BERT has
  an interval that includes zero or lies below it. If JB − BERT still excludes zero above, the
  lead holds at BERT's context.
- **R3.** A Luna lead over Jev on a task is attributed (in part) to the prompt if LP − L1
  excludes zero in the direction that shrinks the lead, and the lead (Jev − LP) then has an
  interval that includes zero or reverses. Jev − LP compares Jev to Luna under Jev's question.
- Refuted predictions stay in RESULTS.md.
