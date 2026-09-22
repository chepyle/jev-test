"""Reproduce the LexGLUE BERT-base baseline on Modal and keep per-example test logits.

Runs coastalcph/lex-glue experiments at a pinned commit with upstream hyperparameters
(bert/patch_upstream.py lists the only code changes). One seed per task; upstream reports
the mean of 5 seeds.

    modal run bert/lexglue_modal.py::bench              # measure throughput, all tasks
    modal run --detach bert/lexglue_modal.py::main --tasks all --seed 1
    modal volume get jev-lexglue-bert runs/<task>/seed_1/test_logits.npy ...

Training resumes from the newest complete epoch checkpoint (model, optimizer, LR scheduler,
RNG, trainer and early-stopping state) after preemption or a relaunch.
"""

import json
import os
import shutil
import subprocess
import threading
import time

import modal

UPSTREAM = "https://github.com/coastalcph/lex-glue"
UPSTREAM_COMMIT = "419a49d0fe82ecb69eb8e9343a9eb3382f1040fd"
TASKS = ("ecthr_a", "ecthr_b", "scotus", "eurlex", "ledgar", "unfair_tos", "case_hold")
GPU = "A100-40GB"

image = (
    modal.Image.debian_slim(python_version="3.10")
    .apt_install("git")
    .pip_install(
        "torch==2.3.1",
        "transformers==4.44.2",
        "accelerate==0.33.0",
        "datasets==2.21.0",
        "scikit-learn==1.5.1",
        "scipy==1.13.1",
        "numpy==1.26.4",
        "nltk==3.8.1",
        "tqdm",
    )
    .run_commands(
        f"git clone {UPSTREAM} /lex-glue && cd /lex-glue && git checkout {UPSTREAM_COMMIT}"
    )
    .add_local_file("bert/patch_upstream.py", "/patch_upstream.py", copy=True)
    .run_commands("python /patch_upstream.py /lex-glue")
    .env({"HF_HOME": "/vol/hf", "TOKENIZERS_PARALLELISM": "false", "PYTHONPATH": "/lex-glue"})
)
volume = modal.Volume.from_name("jev-lexglue-bert", create_if_missing=True)
app = modal.App("jev-lexglue-bert", image=image)


def upstream_args(task: str, seed: int, output_dir: str, epochs: int | None = None) -> list[str]:
    """Command line from coastalcph/lex-glue scripts/run_<task>.sh for one seed.

    run_eurlex.sh says 2 epochs (commit e7a46c9, alongside GPU_NUMBER=6); the original
    script and the authors' runs used 20 with early stopping (coastalcph/lex-glue#21).
    Pass epochs=20 to match the published setup."""
    script = "ecthr" if task.startswith("ecthr") else task
    batch, accumulation = (2, 4) if script in ("ecthr", "scotus") else (8, 1)
    args = ["python", f"experiments/{script}.py"]
    if task == "case_hold":
        args += ["--task_name", task, "--model_name_or_path", "bert-base-uncased"]
    else:
        args += ["--model_name_or_path", "bert-base-uncased", "--do_lower_case", "True"]
        if script == "ecthr":
            args += ["--task", task]
    args += [
        "--output_dir", output_dir, "--do_train", "--do_eval", "--do_pred",
        "--load_best_model_at_end", "--metric_for_best_model", "micro-f1",
        "--greater_is_better", "True", "--evaluation_strategy", "epoch",
        "--save_strategy", "epoch", "--save_total_limit", "5",
        "--num_train_epochs", str(epochs or (2 if task == "eurlex" else 20)),
        "--learning_rate", "3e-5",
        "--per_device_train_batch_size", str(batch), "--per_device_eval_batch_size", str(batch),
        "--seed", str(seed), "--fp16", "--fp16_full_eval",
        "--gradient_accumulation_steps", str(accumulation),
        "--eval_accumulation_steps", str(accumulation),
    ]  # fmt: skip
    return args


def prune_incomplete_checkpoints(output_dir: str) -> None:
    """Drop checkpoints a preemption cut off mid-write, and a run dir with none left."""
    if not os.path.isdir(output_dir):
        return
    required = ("trainer_state.json", "optimizer.pt", "scheduler.pt", "rng_state.pth")
    for name in os.listdir(output_dir):
        path = os.path.join(output_dir, name)
        if name.startswith("checkpoint-") and not all(
            os.path.exists(os.path.join(path, f)) for f in required
        ):
            print(f"removing incomplete {path}", flush=True)
            shutil.rmtree(path)
    if not any(n.startswith("checkpoint-") for n in os.listdir(output_dir)):
        shutil.rmtree(output_dir)


def run_committing(args: list[str], cwd: str) -> int:
    """Run upstream training, committing the volume every 2 minutes so checkpoints persist."""
    stop = threading.Event()

    def committer():
        while not stop.wait(120):
            volume.commit()

    thread = threading.Thread(target=committer, daemon=True)
    thread.start()
    try:
        return subprocess.run(args, cwd=cwd).returncode
    finally:
        stop.set()
        thread.join()
        volume.commit()


@app.function(
    gpu=GPU,
    volumes={"/vol": volume},
    timeout=24 * 3600,
    retries=modal.Retries(max_retries=4, initial_delay=30.0, backoff_coefficient=2.0),
)
def train(task: str, seed: int = 1, epochs: int | None = None) -> dict:
    tag = f"-e{epochs}" if epochs else ""
    output_dir = f"/vol/runs/{task}{tag}/seed_{seed}"
    done = os.path.join(output_dir, "DONE.json")
    volume.reload()
    if os.path.exists(done):
        print(f"{task} seed {seed} already done", flush=True)
        return json.load(open(done))
    started = time.time()
    predicted = all(
        os.path.exists(os.path.join(output_dir, f))
        for f in ("test_logits.npy", "predict_results.json")
    )
    if predicted:
        # Training and test prediction finished; only a post-prediction step failed.
        # Never resume here: resuming a finished run would train extra epochs.
        return finalize(task, seed, output_dir, started)
    if os.path.exists(os.path.join(output_dir, "train_results.json")):
        # Training finished without test logits. Stop instead of retrying into more epochs.
        return {"task": task, "seed": seed, "error": "trained but not predicted; inspect"}
    prune_incomplete_checkpoints(output_dir)
    workdir = f"/vol/work/{task}{tag}"  # CaseHOLD caches features relative to cwd
    os.makedirs(workdir, exist_ok=True)
    for entry in ("experiments", "models"):
        link = os.path.join(workdir, entry)
        if not os.path.exists(link):
            os.symlink(f"/lex-glue/{entry}", link)
    code = run_committing(upstream_args(task, seed, output_dir, epochs), workdir)
    if code != 0:
        raise RuntimeError(f"{task} seed {seed}: upstream script exited {code}")
    if not os.path.exists(os.path.join(output_dir, "test_logits.npy")):
        raise RuntimeError(f"{task} seed {seed}: finished without test_logits.npy")
    return finalize(task, seed, output_dir, started)


def finalize(task: str, seed: int, output_dir: str, started: float) -> dict:
    """Record DONE.json and drop epoch checkpoints (as upstream does after prediction)."""
    for name in os.listdir(output_dir):
        if name.startswith("checkpoint-"):
            shutil.rmtree(os.path.join(output_dir, name))
    done = os.path.join(output_dir, "DONE.json")
    result = {"task": task, "seed": seed, "gpu": GPU, "wall_seconds": time.time() - started}
    for name in ("eval_results.json", "predict_results.json", "train_results.json"):
        path = os.path.join(output_dir, name)
        if os.path.exists(path):
            result[name.removesuffix(".json")] = json.load(open(path))
    with open(done, "w") as fh:
        json.dump(result, fh, indent=2)
    volume.commit()
    return result


@app.function(gpu=GPU, volumes={"/vol": volume}, timeout=3600)
def throughput(task: str, steps: int = 60, fp16: bool = True, logging_steps: int = 10) -> dict:
    """Time `steps` optimizer steps (after data prep) to estimate full-run GPU hours."""
    output_dir = f"/vol/bench/{task}-{steps}{'' if fp16 else '-fp32'}"
    shutil.rmtree(output_dir, ignore_errors=True)
    # Upstream arguments unchanged (EarlyStoppingCallback needs load_best_model_at_end);
    # stop after `steps`, skip test prediction. One validation pass runs at the stop.
    trimmed = [a for a in upstream_args(task, 1, output_dir) if a != "--do_pred"]
    if not fp16:
        trimmed = [a for a in trimmed if a not in ("--fp16", "--fp16_full_eval")]
    trimmed += ["--max_steps", str(steps), "--logging_steps", str(logging_steps)]
    workdir = f"/vol/work/{task}"
    os.makedirs(workdir, exist_ok=True)
    for entry in ("experiments", "models"):
        link = os.path.join(workdir, entry)
        if not os.path.exists(link):
            os.symlink(f"/lex-glue/{entry}", link)
    started = time.time()
    code = run_committing(trimmed, workdir)
    stats = {"task": task, "steps": steps, "exit_code": code, "wall_seconds": time.time() - started}
    for name in ("train_results.json", "eval_results.json"):
        path = os.path.join(output_dir, name)
        if os.path.exists(path):
            stats.update(json.load(open(path)))
    states = sorted(
        (p for p in os.listdir(output_dir) if p.startswith("checkpoint-"))
        if os.path.isdir(output_dir)
        else []
    )
    if states:
        state = json.load(open(os.path.join(output_dir, states[-1], "trainer_state.json")))
        stats["loss_history"] = [h.get("loss") for h in state["log_history"] if "loss" in h]
    return stats


@app.function(gpu=GPU, volumes={"/vol": volume}, timeout=900)
def attention_check() -> dict:
    """Does an all-padding segment (attention mask all zero) produce NaN in fp16 BERT?

    Upstream's HierarchicalBert encodes padding segments and max-pools over all segments,
    so one NaN segment poisons the document representation."""
    import torch
    from transformers import AutoModel

    out = {}
    for impl in ("sdpa", "eager"):
        model = AutoModel.from_pretrained("bert-base-uncased", attn_implementation=impl)
        model = model.cuda().half().eval()
        ids = torch.randint(1000, 2000, (2, 128), device="cuda")
        mask = torch.ones_like(ids)
        mask[1] = 0
        with torch.no_grad():
            hidden = model(input_ids=ids, attention_mask=mask).last_hidden_state
        out[impl] = {
            "real_segment_nan": bool(hidden[0].isnan().any()),
            "padding_segment_nan": bool(hidden[1].isnan().any()),
        }
    out["default_impl"] = AutoModel.from_pretrained("bert-base-uncased").config._attn_implementation
    return out


@app.function(gpu=GPU, volumes={"/vol": volume}, timeout=900)
def hierarchical_check() -> dict:
    """Trace NaN through upstream's HierarchicalBert on two real ECtHR training cases."""
    import sys

    import torch
    from datasets import load_dataset
    from transformers import AutoConfig, AutoModelForSequenceClassification, AutoTokenizer

    sys.path.insert(0, "/lex-glue")
    from models.hierbert import HierarchicalBert

    rows = load_dataset(
        "coastalcph/lex_glue",
        "ecthr_a",
        split="train[:2]",
        revision="c23fdff1a6bf74e0e1a71cb86f1e781d37da888c",
    )
    tok = AutoTokenizer.from_pretrained("bert-base-uncased", do_lower_case=True)
    template = [[0] * 128]
    batch = {"input_ids": [], "attention_mask": [], "token_type_ids": []}
    for case in rows["text"]:
        enc = tok(case[:64], padding="max_length", max_length=128, truncation=True)
        for key in batch:
            batch[key].append(enc[key] + template * (64 - len(enc[key])))
    inputs = {k: torch.tensor(v).cuda() for k, v in batch.items()}
    config = AutoConfig.from_pretrained("bert-base-uncased", num_labels=10)
    trace = {"real_segments": [int(m.any(-1).sum()) for m in inputs["attention_mask"]]}
    for impl in ("sdpa", "eager"):
        for mode in ("train", "eval"):
            torch.manual_seed(0)
            model = AutoModelForSequenceClassification.from_pretrained(
                "bert-base-uncased", config=config, attn_implementation=impl
            )
            model.bert = HierarchicalBert(
                encoder=model.bert, max_segments=64, max_segment_length=128
            )
            model = model.cuda().train(mode == "train")
            with torch.set_grad_enabled(mode == "train"):
                segments = model.bert.encoder(
                    input_ids=inputs["input_ids"].view(-1, 128),
                    attention_mask=inputs["attention_mask"].view(-1, 128),
                    token_type_ids=inputs["token_type_ids"].view(-1, 128),
                )[0]
                logits = model(**inputs).logits
            padding = inputs["attention_mask"].view(-1, 128).sum(-1) == 0
            trace[f"{impl}_{mode}"] = {
                "real_segment_nan": bool(segments[~padding].isnan().any()),
                "padding_segment_nan": bool(segments[padding].isnan().any()),
                "logits_nan": bool(logits.isnan().any()),
            }
    return trace


@app.function(gpu=GPU, volumes={"/vol": volume}, timeout=3600)
def repredict_ecthr(task: str, seed: int = 1) -> dict:
    """Recompute ECtHR val/test logits from the saved best model under fp16 autocast.

    Upstream predicts with --fp16_full_eval, which casts the whole model to half precision
    after training; for ecthr_a seed 1 that produced NaN logits for 951/1000 test cases.
    Training-time evaluation (the regime that selected the best checkpoint) runs fp32
    weights under autocast, so reproducing its validation micro-F1 checks this path."""
    import sys

    import numpy as np
    import torch
    from datasets import load_dataset
    from safetensors.torch import load_file
    from transformers import AutoConfig, AutoModelForSequenceClassification, AutoTokenizer

    sys.path.insert(0, "/lex-glue")
    from models.hierbert import HierarchicalBert

    run = f"/vol/runs/{task}/seed_{seed}"
    config = AutoConfig.from_pretrained(run)
    model = AutoModelForSequenceClassification.from_pretrained(
        "bert-base-uncased", config=config, attn_implementation="eager"
    )
    model.bert = HierarchicalBert(encoder=model.bert, max_segments=64, max_segment_length=128)
    missing = model.load_state_dict(load_file(f"{run}/model.safetensors"), strict=True)
    model = model.cuda().eval()
    tok = AutoTokenizer.from_pretrained(run)
    template = [[0] * 128]
    out = {"load": str(missing)}
    for split in ("validation", "test"):
        rows = load_dataset(
            "coastalcph/lex_glue",
            task,
            split=split,
            revision="c23fdff1a6bf74e0e1a71cb86f1e781d37da888c",
        )
        logits = []
        for start in range(0, len(rows), 8):
            batch = {"input_ids": [], "attention_mask": [], "token_type_ids": []}
            for case in rows[start : start + 8]["text"]:
                enc = tok(case[:64], padding="max_length", max_length=128, truncation=True)
                for key in batch:
                    batch[key].append(enc[key] + template * (64 - len(enc[key])))
            inputs = {k: torch.tensor(v).cuda() for k, v in batch.items()}
            with torch.no_grad(), torch.autocast("cuda", dtype=torch.float16):
                logits.append(model(**inputs).logits.float().cpu().numpy())
        logits = np.concatenate(logits)
        np.save(f"{run}/{split}_logits_autocast.npy", logits)
        out[split] = {
            "rows": len(rows),
            "nan": int(np.isnan(logits).sum()),
            "labels": rows["labels"],
        }
    volume.commit()
    return out


@app.local_entrypoint()
def repredict(task: str = "ecthr_a", seed: int = 1):
    result = repredict_ecthr.remote(task, seed)
    print(json.dumps(result))


@app.local_entrypoint()
def trace():
    print(json.dumps(hierarchical_check.remote(), indent=2))


@app.local_entrypoint()
def check():
    print(json.dumps(attention_check.remote(), indent=2))


@app.local_entrypoint()
def bench(tasks: str = "all", steps: int = 60, fp16: bool = True, logging_steps: int = 10):
    selected = list(TASKS) if tasks == "all" else tasks.split(",")
    kwargs = {"steps": steps, "fp16": fp16, "logging_steps": logging_steps}
    results = list(throughput.map(selected, kwargs=kwargs, return_exceptions=True))
    print(json.dumps([r if isinstance(r, dict) else repr(r) for r in results], indent=2))


@app.local_entrypoint()
def main(tasks: str = "all", seed: int = 1, epochs: int = 0):
    selected = list(TASKS) if tasks == "all" else tasks.split(",")
    kwargs = {"seed": seed, "epochs": epochs or None}
    results = list(train.map(selected, kwargs=kwargs, return_exceptions=True))
    print(json.dumps([r if isinstance(r, dict) else repr(r) for r in results], indent=2))
