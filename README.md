# Jev × LexGLUE

A reproducible **zero-shot** benchmark of [Jev](https://openrouter.ai/~typesafe/jev-latest)
on all seven [LexGLUE](https://github.com/coastalcph/lex-glue) tasks. It freezes official
evaluation examples, sends typed decisions through OpenRouter, checkpoints every completed
request, and writes micro/macro-F1, usage, and cost reports.

Jev uses OpenRouter's [`POST /api/v1/systemone`](https://openrouter.ai/docs/guides/community/typesafe-sdk)
endpoint. Each single-label example becomes one **choice** question. Each multi-label
example becomes one request containing an independent **noul** (yes/no probability)
question per label. No chat completions, output-format prompting, or generated-text parsing
are involved.

The same frozen examples are also scored on two intent-detection tasks (BANKING77, CLINC150)
and against other models through three more routes: self-served open-weight models behind the
same System One API (Kev-4B, LLM2Jev, Clef-flash, elephant-1), chat completions with a JSON
schema (GPT-5.6 Luna), and OpenAI's Decisions API (`gpt-6-luna`). Each route is documented
below; `report/findings.html` collects the comparison.

## Results

Full test split (23,607 examples), zero-shot, micro-F1 arithmetic mean across the 7 tasks:

| Model | Protocol | μ-F1 | m-F1 | Cost³ |
|---|---|---:|---:|---:|
| Jev (`typesafe/jev-1.13-20260917`) | System One | 69.9 | 62.6 | $4.02 |
| Jev, per-label thresholds tuned on validation² | System One | 74.2 | 66.3 | +$2.47 |
| GPT-5.6 Luna (`openai/gpt-5.6-luna`) | chat, JSON schema | 71.3 | 63.9 | $16.45 |
| Kev-4B (`jaredpalmer/kev-4b`, open weights, self-served) | System One | 62.1 | 55.5 | ≤ $8.01 GPU |
| LLM2Jev on Qwen3.5-4B (prompted, no training, self-served) | System One | 62.2 | 53.8 | ≤ $28.84 GPU |
| Clef-flash (`Cloudflare/clef-flash`, open weights, self-served) | System One | 68.3 | 61.3 | ≤ $16.39 GPU |
| elephant-1 (`baselabs/elephant-1`, open weights, self-served) | System One | 71.5 | 63.3 | ≤ $18.13 GPU |
| OpenAI Decisions endpoint (`gpt-6-luna`), LEDGAR on 9,998 of 10,000¹ | Decisions API | 70.5 | 62.4 | $13.02 (computed) |
| BERT-base, fine-tuned (reproduced, seed 1) | supervised | 77.4 | 69.3 | $21.58 GPU |

Jev and Luna are close: Luna is ahead on ECtHR A/B, EUR-LEX, and UNFAIR-ToS, Jev on SCOTUS and
LEDGAR, and CaseHOLD is a tie. Kev-4B, an open-weight 4B model that serves the same API, trails
Jev on all seven tasks (1.9 to 13.3 μ-F1, every paired interval above zero); on Kev's own
held-out suite Jev also leads it by 3.8 points, while Kev-4B leads on its training sources. Jev and Luna both beat fine-tuned BERT on CaseHOLD and trail it
by 12.7 to 32.5 points on EUR-LEX, LEDGAR, and UNFAIR-ToS (Luna 13.3 to 28.6, Jev 12.7 to 32.5). Choosing Jev's per-label thresholds on the
validation split (no test data, no training examples) cuts its gap to BERT from 7.5 to 3.2 μ-F1.
Outside law, Jev trails published fine-tuned BERT on fine-grained intents (BANKING77 80.6 vs
93.7 accuracy; CLINC150 in-scope 89.0 vs 96.7) but finds out-of-scope requests far better
(CLINC150 recall 88.1 vs 59.2). LLM2Jev, which serves a stock Qwen3.5-4B through the same API
with no training, ties Kev-4B on the LexGLUE mean with opposite task profiles (SCOTUS +12.4,
ECtHR A −10.1) and trails it by 7 to 11 points on all four Kev splits, most on rule
application. Cloudflare's Clef-flash (Qwen3.5-9B with a trained schema head) lands between Jev
and Kev-4B on LexGLUE (68.3), ties Kev-4B on Kev's suites, and scores 95.8 BANKING77 accuracy and
98.9 CLINC150 in-scope accuracy, above published fine-tuned BERT (93.66, 96.7); on BANKING77 a pre-registered training-split
probe meets its criterion for exposure, though Clef-flash's near-ceiling accuracy leaves that open. Base Labs' elephant-1 (Qwen3.5-9B post-trained
as a decision model) averages 71.5 μ-F1 on LexGLUE, 1.6 above Jev as a point estimate (ahead on
CaseHOLD +8.1, ECtHR B +4.8, behind on UNFAIR-ToS −3.2), beats Kev-4B on all seven tasks, scores
92.4 BANKING77 accuracy (below Clef-flash and published fine-tuned BERT) and 97.0 [96.5, 97.5]
CLINC150 in-scope accuracy (level with published BERT's 96.7), and is within 3 points of Jev and
Kev-4B on all four Kev splits. OpenAI's Decisions endpoint (`gpt-6-luna`, LexGLUE only) averages
70.5 μ-F1; paired against Jev it leads on ECtHR A, ECtHR B and UNFAIR-ToS and trails on SCOTUS,
EUR-LEX, LEDGAR and CaseHOLD, every interval clear of zero (ECtHR A does not survive a Holm
correction across the 98 paired comparisons, `analysis/multiplicity.json`). [`RESULTS.md`](RESULTS.md) has per-task
intervals, kappa, calibration, paired tests, and caveats, including the protocol difference.

Pre-registered controls (`analysis/PREREG-controls.md`, same documents, paired): a second run moves
Jev and Luna by at most 0.6 μ-F1 per task (Jev is not deterministic for identical requests, but
the spread is small); cut to exactly the text fine-tuned BERT reads, Jev still beats BERT on
SCOTUS (+4.6 [+1.7, +7.4]) but no longer on ECtHR A (+2.1 [−0.1, +4.3]); asked Jev's per-label
questions instead of one select-all question, Luna keeps its ECtHR A, ECtHR B and UNFAIR-ToS
leads, and its EUR-LEX lead goes to −0.8 [−1.9, +0.4]. Across the 98 paired full-test comparisons,
8 intervals that exclude zero do not survive a Holm correction (`analysis/multiplicity.json`),
including Jev over BERT on ECtHR A and Jev over Luna on LEDGAR.

¹ The Decisions API refused two LEDGAR `choice` questions (ledgar/3100, ledgar/9064); they are
excluded from its LEDGAR score. Counting them wrong gives 73.76 instead of 73.77 and leaves the
mean at 70.5. Its multi-label requests omit the true/false criterion sentences that the System One
rows send; see `RESULTS.md`.

² Only this row is tuned: 8 to 100 thresholds per task fitted on the validation split. BERT keeps
upstream's fixed 0.5, chat Luna returns label sets with no probabilities to tune, and every other
row is at 0.5. Compare tuned Jev with the untuned rows as an upper bound for threshold choice, not
as a like-for-like model comparison.

³ The cost column mixes bases: Jev and Luna are OpenRouter-reported request spend; Decisions is
computed from input tokens at $0.10 per 1M uncached (no cost field in the response; cache
discounts not tracked); "≤ … GPU" rows are whole-session Modal billing for serving that model,
including smoke runs, checks, probes and idle scale-down; BERT is single-seed fine-tuning on
Modal. Read them as orders of magnitude, not per-request prices.

## Quick start

Python 3.11+ and [uv](https://docs.astral.sh/uv/) are required. The checked-in lockfile pins
dependencies; the repository's `.python-version` selects Python 3.13.

```bash
uv sync --locked

# Downloads the requested test splits; saves 10 randomly sampled examples per task.
uv run jev-bench prepare --tasks all --limit 10 --output data/quick

# Optional: inspect every request without an API key or inference charges.
uv run jev-bench run --data data/quick --output results/preview --dry-run

# OPENROUTER_API_KEY must be set in your environment.
uv run jev-bench run --data data/quick --output results/quick

# Recompute reports without network access or further API calls.
uv run jev-bench report results/quick
```

Alternatively, copy `.env.example` to `.env`, fill in your key, and use
`uv run --env-file .env jev-bench run ...`. `.env`, cached data, and results are gitignored.
The application reads the key from the environment and never writes it into artifacts.
`jev-test` and `python -m jev_test` are equivalent command entry points.

`prepare` defaults to **10 examples per task**, sampled without replacement with seed 42.
It downloads only the selected split, but the complete Parquet split must be cached even
for a small sample. Inference runs once per selected document; multiple labels share that
one request. Reuse prepared data across model runs to keep the evaluation examples fixed.

## Full benchmark

```bash
uv run jev-bench prepare --tasks all --split test --limit 0 --output data/full-test
uv run jev-bench run --data data/full-test --output results/full-test \
  --model typesafe/jev-1.13 --concurrency 4
```

`--limit 0` selects the complete split: **23,607 test examples / initial API requests**.
Use a concrete model ID for a publishable run. The default is `~typesafe/jev-latest`, matching
the supplied OpenRouter model link. Its target can change; every response's resolved model
ID is recorded, and the runner stops scheduling requests if it observes a version change.
Reports suppress aggregate scores for mixed-model runs.

API calls use your OpenRouter credits. Start with a small sample and inspect reported usage
before running the complete benchmark. No hard spending cap is imposed by this client.

## Tasks and labels

| Task | Decision | Labels | Test examples |
| --- | --- | ---: | ---: |
| `ecthr_a` | ECHR provisions found violated | 10 | 1,000 |
| `ecthr_b` | ECHR provisions allegedly violated | 10 | 1,000 |
| `scotus` | Main Supreme Court issue area | 13 | 1,400 |
| `eurlex` | EuroVoc concepts | 100 | 5,000 |
| `ledgar` | Main contract provision topic | 100 | 10,000 |
| `unfair_tos` | Potentially unfair terms categories | 8 | 1,607 |
| `case_hold` | Correct holding among five candidates | 5 | 3,600 |
| `banking77` | Banking customer intent (not LexGLUE) | 77 | 3,080 |
| `clinc150` | Intent, including out-of-scope (not LexGLUE) | 151 | 5,500 |

Counts and zero-based label order follow the actual
[pinned Hugging Face dataset](https://huggingface.co/datasets/coastalcph/lex_glue/tree/c23fdff1a6bf74e0e1a71cb86f1e781d37da888c).
The older LexGLUE README lists 14 SCOTUS categories and 3,900 CaseHOLD test examples;
this project validates against the released Parquet features and split sizes.

Prompts use readable label descriptions: ECHR article names, SCOTUS issue areas, contract
topics, and [English EuroVoc descriptors](https://github.com/nlpaueb/multi-eurlex/blob/078092d62633ab1fc85065cc5937e60edd805095/data/eurovoc_descriptors.json).
The bundled catalog preserves the original codes and their exact dataset index order.
CaseHOLD uses the five provided holding statements as its choice criteria.

```bash
uv run jev-bench tasks
uv run jev-bench prepare --tasks scotus case_hold --limit 100 --seed 7 --output data/subset
uv run jev-bench prepare --tasks unfair_tos --split validation --limit 0 --output data/dev
uv run jev-bench prepare --tasks banking77 clinc150 --limit 0 --output data/intents-test
```

`--tasks all` means the seven LexGLUE tasks; the intent tasks are always named explicitly and
never enter the LexGLUE aggregate.

## Evaluation protocol

- **Zero-shot:** no training examples, retrieval, fine-tuning, or few-shot demonstrations.
  Only document text and candidate label descriptions enter API requests. Gold answers
  stay local for scoring. This is a different training regime from the supervised models
  in the [LexGLUE leaderboard](https://github.com/coastalcph/lex-glue#leaderboard).
- **Multi-label selection:** a label is selected when its noul probability is strictly
  greater than `--threshold` (default `0.5`). Tune prompts or thresholds on validation
  data, then freeze settings before evaluating test data.
- **Metrics:** micro-F1 and macro-F1 follow the
  [upstream experiment scripts](https://github.com/coastalcph/lex-glue/tree/main/experiments).
  ECtHR A/B and UNFAIR-ToS add a synthetic none-of-the-above column for empty label sets.
  EUR-LEX does not. Multi-label macro-F1 includes all label columns; single-label macro-F1
  uses the union of observed gold/predicted classes, as upstream. Zero-division scores are
  zero. CaseHOLD reports both F1 variants; macro-F1 need not equal accuracy.
- **Aggregates:** arithmetic, harmonic, and geometric means across the selected tasks.
  A `lexglue_aggregate` is emitted only for all seven complete test splits with one resolved
  model. Small samples receive an explicitly labeled `selected_tasks_aggregate`.
- **Long documents:** by default, retain the head and tail within 48,000 characters,
  including an omission marker. Record each example's original/sent lengths and truncation
  status. CaseHOLD candidate holdings are always preserved. `--max-chars 0` sends complete
  text; `--max-chars 24000` reduces the cap. This character cap is not an exact token budget
  or a guarantee of fitting the model context: questions and choices also consume tokens.
  The truncation protocol differs from upstream model-specific tokenization.
- **Failures:** malformed/missing answers, API failures, and interrupted requests never
  become empty or default predictions. Partial task scores use successful examples only,
  clearly report coverage, and are diagnostic. Incomplete runs have no aggregate score.

No claim is made about Jev's training-data overlap with this public benchmark. Publish
the run settings, truncation counts, and model IDs alongside any accuracy comparison.

## Other models (chat protocol)

OpenRouter's System One endpoint serves TypeSafe models only. Open-weight models that serve the
same API are self-hosted (see Kev's suites, LLM2Jev, and Clef-flash and elephant-1 below) and
take `--endpoint`. To score another OpenRouter model on the same examples:

```bash
uv run jev-bench run --data data/full-test --output results/luna-full \
  --model openai/gpt-5.6-luna --protocol chat --concurrency 12
```

`--protocol chat` sends the same task instructions, label descriptions and truncation over
`/chat/completions` with a strict JSON schema. The answer is generated text parsed as JSON;
multi-label tasks return a label set, so there are no probabilities and `--threshold` does not
apply. Refusals and malformed answers are recorded as errors, never as default predictions.
The multi-label question is not the same as System One's: `chat` appends "Select every option
that applies, or none." and lists bare numbered options, while System One asks one yes/no
question per label ("Does this label apply: …?") with true/false criterion sentences.
`--protocol chat-perlabel` asks System One's per-label questions and criteria over chat (one
boolean per label in the schema); it is the control for that difference (multi-label tasks
only; results in `RESULTS.md`).

### OpenAI Decisions API

`--protocol decisions` calls `POST https://api.openai.com/v1/decisions` (model `gpt-6-luna`,
key from `OPENAI_API_KEY`): one `predicate` per label for multi-label tasks, one `choice` for
single-label tasks, probabilities returned. Predicate questions carry no true/false criterion
sentences, unlike System One `noul` questions, so multi-label comparisons include that request
difference. A refused `choice` is recorded as a failed example; a refused `predicate` is imputed
as not applied (p = 0). Use `scripts/run_decisions.py` for a resumable, heartbeat-publishing run:

```bash
uv run scripts/run_decisions.py --job-id decisions-full --data data/full-test \
  --output results/decisions-full --total 23607 --concurrency 6   # add --resume to continue
```

`--resume` re-sends only unfinished and failed examples. A run whose only failures are refusals
closes as done (refusals repeat on retry) and its report withholds the aggregate. The full run
peaked at 2.05 GiB RSS. Results are in `RESULTS.md`.

## Detailed analysis

```bash
uv run jev-bench analyze --source jev=results/full-test/predictions.jsonl \
  --output analysis/full-test.json
```

Adds Cohen's kappa (per label for multi-label tasks), MCC, precision/recall, top-3 accuracy,
ROC-AUC, calibration (ECE, Brier), length/truncation breakdowns, and bootstrap intervals.
Repeat `--source NAME=PATH` to compare prediction ledgers on shared examples: inter-model
kappa, McNemar exact test, and paired bootstrap F1 differences. See `RESULTS.md`.

Bootstrap draws depend only on the records: ledgers are sorted by example id (they are written
in async completion order) and each task gets a fresh generator, so two models scored on the
same examples resample the same items. Every derived file in `analysis/` is rebuilt from the
ledgers by one script (no network; `RESUME=1` skips outputs already written):

```bash
scripts/regenerate_analysis.sh                   # analyze + paired ROC-AUC files
uv run python clef_bench/train_probe.py score > analysis/clef-flash-train-probe.json
uv run python analysis/decisions_refusal_sensitivity.py > analysis/decisions-refusal-sensitivity.json
uv run python analysis/multiplicity.py > analysis/multiplicity.json   # Holm across comparisons
uv run python kev_suites/summarize.py > analysis/kev-suites.md
scripts/control_analyses.sh                      # redraw, context and prompt controls
uv run python report/build_report.py
```

Numbers shown in tables are rounded once, half to even, from the shortest decimal form of the
raw value (`jev_test.fmt`), in `report.md`, the Kev-suite tables and the HTML report alike.

### Controls

Pre-registered in `analysis/PREREG-controls.md`; results in `RESULTS.md`.

```bash
# Jev on the text fine-tuned BERT reads (upstream LexGLUE limits, bert-base-uncased tokens)
uv run --with tokenizers python bert/context_matched.py data/full-test data/full-test-bertctx
uv run python scripts/prepare_control_subset.py data/full-test data/control-full \
  ecthr_a ecthr_b scotus unfair_tos eurlex:500
uv run python scripts/prepare_control_subset.py data/full-test-bertctx data/control-bertctx \
  ecthr_a ecthr_b scotus eurlex:500
uv run python scripts/prepare_control_subset.py data/full-test data/multilabel-control \
  ecthr_a ecthr_b unfair_tos eurlex:500
uv run jev-bench run --data data/control-full --output results/jev-redraw --model typesafe/jev-1.13
uv run jev-bench run --data data/control-bertctx --output results/jev-bertctx \
  --model typesafe/jev-1.13 --max-chars 0
uv run jev-bench run --data data/multilabel-control --output results/luna-redraw \
  --model openai/gpt-5.6-luna --protocol chat --concurrency 16
uv run jev-bench run --data data/multilabel-control --output results/luna-perlabel \
  --model openai/gpt-5.6-luna --protocol chat-perlabel --concurrency 16
```

## Resume and failure recovery

```bash
# Continue after interruption without paying again for checkpointed successes.
uv run jev-bench run --data data/quick --output results/quick --resume

# Explicitly retry failed examples as well as unfinished ones.
uv run jev-bench run --data data/quick --output results/quick --resume --retry-failed
```

Repeat the original model, threshold, endpoint, and character-cap options when resuming.
Resume verifies the data manifest, data checksums, protocol source hash, request hashes,
and saved configuration before sending requests. A changed experiment needs a new output
directory. Concurrency, timeout, and retry count can change on resume.

Requests retry transport failures and HTTP 408/429/500/502/503/504 with backoff, up to
`--retries 4` additional attempts. Permanent errors such as 401/402 stop the run immediately;
other workers already in flight can finish and checkpoint. Exhausted retries or invalid
responses also stop new work. Incomplete/mixed runs exit with code 2; interruption exits 130.

Only one writer may use a run directory at a time. Checkpoints are flushed and synced after
each completed call. Resume repairs an incomplete last JSONL line after an abrupt shutdown;
corruption elsewhere is rejected. A request interrupted after the server processed it but
before its checkpoint may be charged again on resume. Retry costs without returned usage
cannot be recovered from the client ledger.

## Artifacts

Prepared data contains `manifest.json` plus one normalized JSONL file per task. The manifest
records dataset revision, label-catalog hash, split, seed, exact row indices, fingerprints,
and file checksums. Data preparation is pinned to revision
`c23fdff1a6bf74e0e1a71cb86f1e781d37da888c`; it executes no remote dataset scripts.

Each run directory contains:

| File | Contents |
| --- | --- |
| `manifest.json` | Dataset snapshot metadata, settings, protocol hash, package versions |
| `predictions.jsonl` | Append-only responses, gold/predicted labels, probabilities, model IDs, request hashes, errors, usage, latency |
| `metrics.json` | Task metrics, coverage, aggregates, truncation, and reported API cost |
| `metrics.csv` | One row per task; F1 values in `[0, 1]` |
| `report.md` | Readable report with F1 displayed as percentages |

Dry runs instead produce `requests.jsonl` and `preview.json`. Use a separate output directory
for previews. Local artifacts contain public dataset excerpts and model responses; keep
the prepared data alongside your run if you want to reconstruct requests later.

`reported_cost_usd` sums `usage.cost` returned by OpenRouter, including recorded responses
that failed validation. It is `null` if no costs were returned, and is not a billing estimate
for missing or retried responses. Latency includes client retries/backoff; concurrency affects
it, so it should not be interpreted as isolated model inference latency.

## Kev's suites

[Kev](https://github.com/jaredpalmer/kev) is an open-weight model family that serves the System
One API. Kev-4B is served on Modal with Kev's own deploy script and scored on LexGLUE and the
intent suite with the same `jev-bench run` requests as Jev. `kev_suites/` scores Jev, GPT-5.6
Luna and Kev-4B on Kev's frozen `transfer-v4` and `decision-v7` suites with Kev's own scorer,
and holds the matching scripts for the encoder, LLM2Jev, Clef-flash and elephant-1 (below).
Kev is cloned at a pinned commit into the git-ignored `third_party/`. Luna goes through
`jev_test.chatshim`, a local System One endpoint backed by chat JSON, which caches answers so a
rerun makes no new calls. Results in [`RESULTS.md`](RESULTS.md).

```bash
git clone https://github.com/jaredpalmer/kev third_party/kev && git -C third_party/kev checkout 5920c5f
(cd third_party/kev && uv sync --locked)
kev_suites/run_jev.sh
uv run python -m jev_test.chatshim --model openai/gpt-5.6-luna --cache results/kev-suites/luna-cache &
kev_suites/run_luna.sh
# Kev-4B endpoint: bearer key in a Modal secret, 64k-token context from Kev 5920c5f
uvx modal secret create kev-serve-key KEV_API_KEY="$KEV_API_KEY"
(cd third_party/kev/skills/kev-finetune/scripts && KEV_REF=5920c5fe4ca8e0970ed4209ac2c9b8e18bea5109 \
  KEV_APP_NAME=jev-test-kev KEV_SERVE_GPU=L40S KEV_SERVE_SECRET=kev-serve-key uvx modal deploy kev_modal.py)
KEV_URL=https://<workspace>--jev-test-kev-api.modal.run kev_suites/run_kev.sh
uv run python kev_suites/summarize.py > analysis/kev-suites.md
# LexGLUE and intents: the runner sends its key from OPENROUTER_API_KEY
OPENROUTER_API_KEY=$KEV_API_KEY uv run python jobs/launch.py kev4b-full data/full-test results/kev4b-full \
  --model kev-latest --endpoint "$KEV_URL/v1/systemone" --concurrency 24 --timeout 300
```

### Fine-tuned encoder on Kev's training data

`encoder/` fine-tunes ModernBERT-large as a cross-encoder (one scored pair per option) on
Kev's `decision-v7` train partition, the data Kev-4B trained on, and scores it on Kev's
suites with Kev's scorer. Training and prediction run on Modal; scoring is local.

```bash
(cd third_party/kev && uv run python -c "from kev.suite import load_split; load_split('evals/v7/decision-v7', 'train')")
uvx modal run encoder/modal_app.py::bench --steps 40
uvx modal run --detach encoder/modal_app.py::train --name mbl-s1   # relaunch the same command to resume
uvx modal run encoder/modal_app.py::predict --name mbl-s1
uvx modal volume get jev-kev-encoder runs/mbl-s1/logits.jsonl results/kev-encoder/mbl-s1/
kev_suites/run_encoder.sh mbl-s1
uv run python kev_suites/summarize.py > analysis/kev-suites.md
```

### LLM2Jev: a prompted open model behind the same API

[LLM2Jev](https://github.com/Yinsongxu/LLM2Jev) serves any local chat model as a System One
endpoint without training: each candidate becomes one yes/no prompt, P(yes) comes from the
next-token logits of a zero-token prefill, and choice candidates are normalized to sum to one.
`llm2jev_bench/modal_app.py` runs its own `llm2jev-serve --backend sglang` (commit `a4aafa8`,
SGLang 0.5.20) with Qwen3.5-4B on a Modal H100, and the LexGLUE, intent and Kev-suite runs send
it the same requests as Jev.

```bash
git clone https://github.com/fstandhartinger/jevbench third_party/jevbench && git -C third_party/jevbench checkout 9ec6f15
uvx modal secret create llm2jev-serve-key LLM2JEV_API_KEY="$LLM2JEV_API_KEY"
uvx modal run llm2jev_bench/modal_app.py::download
# staged prefix reuse (served) vs no prefix cache, on 27 real requests
uv run python llm2jev_bench/payloads.py data/smoke50 data/intents-smoke --per-task 3 \
  --output results/llm2jev/prefix-payloads.jsonl
uvx modal run llm2jev_bench/modal_app.py::prefix_check --payloads results/llm2jev/prefix-payloads.jsonl
uv run python llm2jev_bench/compare_configs.py results/llm2jev/prefix-check.json staged reference
uvx modal deploy llm2jev_bench/modal_app.py
LLM2JEV_URL=https://<workspace>--jev-test-llm2jev-api.modal.run
# serving check against LLM2Jev's published JevBench number (run inside third_party/jevbench)
python -m jevbench.cli run --tasks datasets/public/original.jsonl,datasets/public/easy.jsonl,datasets/public/hard.jsonl \
  --adapter typesafe --endpoint "$LLM2JEV_URL" --key-env LLM2JEV_API_KEY --model qwen3.5-4b \
  --cost-basis self_hosted_modal_h100 --reserve-usd 0 --results <out>/results.jsonl
OPENROUTER_API_KEY=$LLM2JEV_API_KEY uv run python jobs/launch.py llm2jev-full data/full-test \
  results/llm2jev-full --model qwen3.5-4b --endpoint "$LLM2JEV_URL/v1/systemone" --concurrency 32 --timeout 600
OPENROUTER_API_KEY=$LLM2JEV_API_KEY uv run python jobs/launch.py llm2jev-intents data/intents-test \
  results/llm2jev-intents-test --model qwen3.5-4b --endpoint "$LLM2JEV_URL/v1/systemone" --concurrency 16 --timeout 600
LLM2JEV_URL=$LLM2JEV_URL kev_suites/run_llm2jev.sh
llm2jev_bench/analyze.sh
```

### Clef-flash and elephant-1: open-weight decision models on Modal

`clef_bench/modal_app.py` serves Cloudflare's Clef-flash with the release's own `systemone`
function; `elephant_bench/modal_app.py` serves Base Labs' elephant-1 with the model repo's own
`setup.sh`. Both are Qwen3.5-9B models on an H100, behind a bearer key taken from the existing
`llm2jev-serve-key` Modal secret (`LLM2JEV_API_KEY` locally), and receive the same requests as
Jev. The run scripts read `.env`, resume from their ledgers when re-run, and default to the
original deployment's URL; set `CLEF_URL` or `ELEPHANT_URL` to your own.

```bash
uvx modal run clef_bench/modal_app.py::download
uvx modal deploy clef_bench/modal_app.py
CLEF_URL=https://<workspace>--jev-test-clef-flash-server-api.modal.run
CLEF_URL=$CLEF_URL clef_bench/run.sh clef-full data/full-test results/clef-flash-full
CLEF_URL=$CLEF_URL clef_bench/run.sh clef-intents data/intents-test results/clef-flash-intents-test
CLEF_URL=$CLEF_URL kev_suites/run_clef.sh
clef_bench/analyze.sh

uvx modal run elephant_bench/modal_app.py::download
uvx modal deploy elephant_bench/modal_app.py
ELEPHANT_URL=https://<workspace>--jev-test-elephant-server-api.modal.run
ELEPHANT_URL=$ELEPHANT_URL elephant_bench/run_all.sh   # intents, LexGLUE, then Kev's suites
elephant_bench/analyze.sh
```

elephant-1's card says requests over 16,384 tokens are refused; the server returns them as
HTTP 422 so they count as failures. The full runs had none (`RESULTS.md`). `clef_bench/PREREG-train-probe.md` and `clef_bench/train_probe.py` are the
pre-registered test of whether Clef-flash trained on BANKING77 and CLINC150; the probe script
keeps the original deployment URL it was registered with.

## Fine-tuned BERT baseline

`bert/` reproduces the LexGLUE BERT-base baseline with the upstream
[`coastalcph/lex-glue`](https://github.com/coastalcph/lex-glue) scripts (commit `419a49d`) on
[Modal](https://modal.com) GPUs, keeping per-example test logits for paired comparison with Jev.
It needs a Modal account and runs from its own environment (`uvx modal`); it is not a project
dependency.

```bash
uvx modal run bert/lexglue_modal.py::bench --steps 60   # throughput, for a cost estimate
uvx modal run --detach bert/lexglue_modal.py::main --tasks all --seed 1
uvx modal run --detach bert/lexglue_modal.py::main --tasks eurlex --seed 1 --epochs 20
uvx modal volume get jev-lexglue-bert runs/<task>/seed_1/test_logits.npy \
  results/bert-seed1/logits/<task>/
uv run python bert/export_predictions.py --logits results/bert-seed1/logits \
  --data data/full-test --output results/bert-seed1/predictions.jsonl
uv run jev-bench analyze --source jev=results/full-test/predictions.jsonl \
  --source bert=results/bert-seed1/predictions.jsonl --output analysis/jev-vs-bert.json
uv run python analysis/paired_auc.py results/full-test/predictions.jsonl \
  results/bert-seed1/predictions.jsonl > analysis/paired-auc.json
```

- `patch_upstream.py` lists every change to the upstream code. It loads the pinned Parquet
  release, saves test logits, uses eager attention for the hierarchical ECtHR/SCOTUS models
  (SDPA returns NaN on all-padding segments), and fixes three incompatibilities with
  transformers 4.44. Hyperparameters are upstream's.
- Training checkpoints every epoch (model, optimizer, LR scheduler, RNG, early-stopping state)
  to the `jev-lexglue-bert` volume and resumes after preemption. A finished run is finalized,
  never resumed, so a retry cannot add epochs.
- `repredict` recomputes ECtHR test logits under fp16 autocast, from the saved best model,
  when upstream's `--fp16_full_eval` returns NaN.
- `check` and `trace` are the attention-NaN diagnostics behind the eager-attention patch.

Seed 1 cost $21.58 on A100-40GB and lands within 1.1 μ-F1 of the published 5-seed means.
Upstream's `run_eurlex.sh` trains 2 epochs, which under-fits (66.5 / 33.9); use `--epochs 20`
(see `RESULTS.md` and coastalcph/lex-glue#21).

`jobs/launch.py` supervises a long `jev-bench run` (heartbeats, 30 s+ backoff relaunch on
throttles, hard stop on 401/402). It and `scripts/run_decisions.py` import a local `jobstate`
helper that is not in this repository.

## Findings report

```bash
uv run python report/build_report.py
```

Renders `report/template.html` into `report/findings.html` from the committed `analysis/*.json`
files and the run ledgers under `results/`. Means are computed from unrounded per-task scores,
the script asserts them against the values in `RESULTS.md`, and the page's "results as of"
commit is the last commit that touched `analysis/`.

## Development

```bash
uv sync --locked
uv run pytest -q
D="src tests bert analysis scripts report kev_suites clef_bench elephant_bench llm2jev_bench encoder jobs"
uv run ruff check $D
uv run ruff format --check $D
```

Tests use synthetic data and a mocked HTTP transport and require no credentials or network.
They check reference metric edge cases, request isolation from gold labels, strict response
validation, error handling, dataset integrity, resuming, and all seven task paths.

Code lives in `src/jev_test`: `data.py` freezes datasets, `tasks.py` and `questions.py` define
the protocol, `client.py` calls System One, `chat.py` and `decisions.py` hold the chat and Decisions
protocols, `chatshim.py` serves a chat model as a local System One endpoint, `runner.py` and
`storage.py` checkpoint inference, `metrics.py`/`report.py` score results, and `analysis.py`
adds kappa, calibration, and paired comparisons. `assets/labels.json` includes label-source attribution.

## Sources and attribution

- [Chalkidis et al. (2022), LexGLUE](https://aclanthology.org/2022.acl-long.297/), ACL 2022,
  pp. 4310–4330. Cite this paper when publishing benchmark results.
- [LexGLUE dataset card and licensing](https://huggingface.co/datasets/coastalcph/lex_glue):
  the card declares CC BY 4.0; consult it for the underlying dataset sources.
- [MultiEURLEX](https://github.com/nlpaueb/multi-eurlex): source of the bundled English
  EuroVoc descriptor subset. Labels were extracted from commit
  `078092d62633ab1fc85065cc5937e60edd805095`.
- [OpenRouter System One integration](https://openrouter.ai/docs/guides/community/typesafe-sdk)
  and [TypeSafe primitives](https://docs.typesafe.ai/primitives) define the API contract.

## License

Code in this repository is licensed under the [Apache License 2.0](LICENSE). Label names and
descriptions bundled in `src/jev_test/assets/` come from LexGLUE (CC BY 4.0), MultiEURLEX
EuroVoc descriptors (CC BY-SA 4.0), BANKING77 (CC BY 4.0), and CLINC150 (CC BY 3.0), and remain
under those terms; see [NOTICE](NOTICE). Benchmark datasets are downloaded at run time, not
redistributed.
