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

## Results

Full test split (23,607 examples), zero-shot, micro-F1 arithmetic mean across the 7 tasks:

| Model | Protocol | μ-F1 | m-F1 | Cost |
|---|---|---:|---:|---:|
| Jev (`typesafe/jev-1.13-20260917`) | System One | 69.9 | 62.6 | $4.02 |
| Jev, per-label thresholds tuned on validation | System One | 74.2 | 66.3 | +$2.47 |
| GPT-5.6 Luna (`openai/gpt-5.6-luna`) | chat, JSON schema | 71.3 | 63.9 | $16.45 |
| BERT-base, fine-tuned (reproduced, seed 1) | supervised | 77.4 | 69.3 | $21.58 GPU |

The two zero-shot models are close: Luna is ahead on ECtHR A/B, EUR-LEX, and UNFAIR-ToS, Jev on
SCOTUS and LEDGAR, and CaseHOLD is a tie. Both beat fine-tuned BERT on CaseHOLD and trail it by
13 to 29 points on EUR-LEX, LEDGAR, and UNFAIR-ToS. Choosing Jev's per-label thresholds on the
validation split (no test data, no training examples) cuts its gap to BERT from 7.5 to 3.2 μ-F1.
Outside law, Jev trails published fine-tuned BERT on fine-grained intents (BANKING77 80.7 vs
93.7 accuracy; CLINC150 in-scope 89.0 vs 96.7) but finds out-of-scope requests far better
(CLINC150 recall 88.1 vs 59.2). [`RESULTS.md`](RESULTS.md) has per-task
intervals, kappa, calibration, paired tests, and caveats, including the protocol difference.

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
```

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

System One serves TypeSafe models only. To score another OpenRouter model on the same examples:

```bash
uv run jev-bench run --data data/full-test --output results/luna-full \
  --model openai/gpt-5.6-luna --protocol chat --concurrency 12
```

`--protocol chat` asks the same questions (instructions, label descriptions, truncation) over
`/chat/completions` with a strict JSON schema. The answer is generated text parsed as JSON;
multi-label tasks return a label set, so there are no probabilities and `--threshold` does not
apply. Refusals and malformed answers are recorded as errors, never as default predictions.

## Detailed analysis

```bash
uv run jev-bench analyze --source jev=results/full-test/predictions.jsonl \
  --output analysis/full-test.json
```

Adds Cohen's kappa (per label for multi-label tasks), MCC, precision/recall, top-3 accuracy,
ROC-AUC, calibration (ECE, Brier), length/truncation breakdowns, and bootstrap intervals.
Repeat `--source NAME=PATH` to compare prediction ledgers on shared examples: inter-model
kappa, McNemar exact test, and paired bootstrap F1 differences. See `RESULTS.md`.

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
throttles, hard stop on 401/402). It imports a local `jobstate` helper that is not in this
repository.

## Development

```bash
uv sync --locked
uv run pytest -q
uv run ruff check src tests bert analysis
uv run ruff format --check src tests bert analysis
```

Tests use synthetic data and a mocked HTTP transport and require no credentials or network.
They check reference metric edge cases, request isolation from gold labels, strict response
validation, error handling, dataset integrity, resuming, and all seven task paths.

Code lives in `src/jev_test`: `data.py` freezes datasets, `tasks.py` and `questions.py` define
the protocol, `client.py` calls System One, `runner.py` checkpoints inference, and
`metrics.py`/`report.py` score results, and `analysis.py` adds kappa, calibration, and paired
comparisons. `assets/labels.json` includes label-source attribution.

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
