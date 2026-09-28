"""Fine-tune ModernBERT-large as a cross-encoder on Kev's training split, on Modal.

Kev-4B trained on Kev's `decision-v7` train partition; this trains an encoder on the same
records (see encoder/crossenc.py for the pair framing) and selects the checkpoint on
`decision-v7` development, as Kev does. Prediction writes raw per-option logits for every
record of both suites' dev/test and decision-v7 calibration, so the temperature is fitted
and every score is computed locally (encoder/score.py) by Kev's own scorer.

    uvx modal run encoder/modal_app.py::bench --steps 40
    uvx modal run --detach encoder/modal_app.py::train --name mbl-s1
    uvx modal run encoder/modal_app.py::predict --name mbl-s1
    uvx modal run encoder/modal_app.py::predict --name nli-zeroshot \
        --model MoritzLaurer/ModernBERT-large-zeroshot-v2.0 --scorer nli
    uvx modal volume get jev-kev-encoder runs/<name>/logits.jsonl results/kev-encoder/<name>/

Training checkpoints model, optimizer, LR scheduler, data position and RNG every
CKPT_EVERY steps and resumes from the newest one when relaunched with the same name.
"""

import json
import os
import random
import sys
import time

import modal

GPU = "H100"
BASE = "answerdotai/ModernBERT-large"
BASE_REVISION = "45bb4654a4d5aaff24dd11d4781fa46d39bf8c13"
NLI = "MoritzLaurer/ModernBERT-large-zeroshot-v2.0"
NLI_REVISION = "a51e07b524299e309dd2b88d48b0cfa2bd9ec598"
CKPT_EVERY = 200
SUITES = {
    "decision-v7": ("development", "test", "calibration"),
    "transfer-v4": ("development", "test"),
}

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("torch==2.8.0", "transformers==5.17.0", "numpy==2.3.3", "accelerate==1.15.0")
    .env({"HF_HOME": "/vol/hf", "TOKENIZERS_PARALLELISM": "false", "PYTHONUNBUFFERED": "1"})
    .add_local_file("encoder/crossenc.py", "/app/crossenc.py")
    .add_local_dir("third_party/kev/evals/v7/decision-v7", "/data/decision-v7")
    .add_local_dir("third_party/kev/evals/v4/transfer-v4", "/data/transfer-v4")
)
volume = modal.Volume.from_name("jev-kev-encoder", create_if_missing=True)
app = modal.App("jev-kev-encoder", image=image)


def load(suite: str, split: str) -> list[dict]:
    with open(f"/data/{suite}/{split}.jsonl") as fh:
        return [json.loads(line) for line in fh]


def items(records):
    """(pairs, gold index) per question; pairs from the request fields only."""
    from crossenc import api_request, label_index, pairs

    out = []
    for record in records:
        request = api_request(record)
        for (_, _, _, pp), q in zip(pairs(request), record["questions"].values(), strict=True):
            out.append((pp, label_index(q)))
    return out


def packs(questions, order, budget):
    """Consecutive questions from `order` grouped so each pack holds <= budget pairs."""
    pack, size = [], 0
    for i in order:
        n = len(questions[i][0])
        if pack and size + n > budget:
            yield pack
            pack, size = [], 0
        pack.append(i)
        size += n
    if pack:
        yield pack


class Scorer:
    def __init__(self, model_id, scorer="head", revision=None, path=None):
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        self.torch, self.kind = torch, scorer
        self.tok = AutoTokenizer.from_pretrained(model_id, revision=revision)
        kwargs = {"num_labels": 1} if scorer == "head" else {}
        self.model = AutoModelForSequenceClassification.from_pretrained(
            path or model_id, revision=None if path else revision, **kwargs
        ).cuda()
        if scorer == "nli":
            labels = {v.lower(): int(k) for k, v in self.model.config.id2label.items()}
            self.entail, self.other = labels["entailment"], labels["not_entailment"]

    def logits(self, flat_pairs):
        from crossenc import MAX_LENGTH

        enc = self.tok(
            [a for a, _ in flat_pairs],
            [b for _, b in flat_pairs],
            truncation="only_first",
            max_length=MAX_LENGTH,
            padding=True,
            return_tensors="pt",
        ).to("cuda")
        with self.torch.autocast("cuda", dtype=self.torch.bfloat16):
            out = self.model(**enc).logits.float()
        if self.kind == "nli":
            return out[:, self.entail] - out[:, self.other]
        return out[:, 0]


def group_loss(torch, logits, sizes, golds):
    losses, start = [], 0
    for n, g in zip(sizes, golds, strict=True):
        losses.append(
            torch.nn.functional.cross_entropy(
                logits[start : start + n][None], torch.tensor([g], device=logits.device)
            )
        )
        start += n
    return torch.stack(losses).mean()


def accuracy(scorer, questions, budget):
    torch = scorer.torch
    scorer.model.eval()
    right = 0
    with torch.no_grad():
        for pack in packs(questions, range(len(questions)), budget):
            flat = [p for i in pack for p in questions[i][0]]
            lg, start = scorer.logits(flat), 0
            for i in pack:
                n = len(questions[i][0])
                right += int(lg[start : start + n].argmax().item() == questions[i][1])
                start += n
    scorer.model.train()
    return right / len(questions)


def save_ckpt(path, scorer, opt, sched, state):
    torch = scorer.torch
    tmp = path + ".tmp"
    os.makedirs(tmp, exist_ok=True)
    torch.save(
        {
            "model": scorer.model.state_dict(),
            "opt": opt.state_dict(),
            "sched": sched.state_dict(),
            "state": state,
            "rng": {
                "py": random.getstate(),
                "torch": torch.get_rng_state(),
                "cuda": torch.cuda.get_rng_state_all(),
            },
        },
        f"{tmp}/ckpt.pt",
    )
    if os.path.exists(path):
        os.rename(path, path + ".old")
    os.rename(tmp, path)
    if os.path.exists(path + ".old"):
        import shutil

        shutil.rmtree(path + ".old")
    volume.commit()


def log(run_dir, **fields):
    fields["ts"] = time.time()
    print(json.dumps(fields), flush=True)
    with open(f"{run_dir}/log.jsonl", "a") as fh:
        fh.write(json.dumps(fields) + "\n")


@app.function(
    gpu=GPU,
    volumes={"/vol": volume},
    timeout=6 * 3600,
    retries=modal.Retries(max_retries=3, initial_delay=30.0),
)
def train_remote(
    name, lr=2e-5, epochs=2, seed=1, budget=128, warmup=0.06, eval_every=400, max_steps=0
):
    """Resumable fine-tune; `max_steps` > 0 stops early (bench)."""
    sys.path.insert(0, "/app")
    import torch
    from transformers import get_linear_schedule_with_warmup

    run_dir = f"/vol/runs/{name}"
    os.makedirs(run_dir, exist_ok=True)
    config = dict(
        name=name,
        base=BASE,
        revision=BASE_REVISION,
        lr=lr,
        epochs=epochs,
        seed=seed,
        budget=budget,
        warmup=warmup,
        eval_every=eval_every,
        max_steps=max_steps,
    )
    cfg_path = f"{run_dir}/config.json"
    if os.path.exists(cfg_path) and not max_steps:
        assert json.load(open(cfg_path)) == config, "run name reused with a different config"
    json.dump(config, open(cfg_path, "w"), indent=2)

    random.seed(seed)
    torch.manual_seed(seed)
    train_q = items(load("decision-v7", "train"))
    dev_q = items(load("decision-v7", "development"))
    orders = []
    for epoch in range(epochs):
        order = list(range(len(train_q)))
        random.Random(seed * 1000 + epoch).shuffle(order)
        orders.append(list(packs(train_q, order, budget)))
    total = sum(len(o) for o in orders)
    if max_steps:
        total = min(total, max_steps)

    scorer = Scorer(BASE, "head", revision=BASE_REVISION)
    opt = torch.optim.AdamW(scorer.model.parameters(), lr=lr, weight_decay=0.01)
    sched = get_linear_schedule_with_warmup(opt, int(warmup * total), total)
    state = {"step": 0, "best": -1.0, "best_step": None}
    ckpt = f"{run_dir}/ckpt"
    if os.path.exists(f"{ckpt}/ckpt.pt") and not max_steps:
        blob = torch.load(f"{ckpt}/ckpt.pt", map_location="cpu", weights_only=False)
        scorer.model.load_state_dict(blob["model"])
        opt.load_state_dict(blob["opt"])
        sched.load_state_dict(blob["sched"])
        state = blob["state"]
        random.setstate(blob["rng"]["py"])
        torch.set_rng_state(blob["rng"]["torch"])
        torch.cuda.set_rng_state_all(blob["rng"]["cuda"])
        log(run_dir, event="resumed", step=state["step"], best=state["best"])

    scorer.model.train()
    step, started, pairs_seen = 0, time.time(), 0
    for epoch, epoch_packs in enumerate(orders):
        for pack in epoch_packs:
            step += 1
            if step <= state["step"]:
                continue  # already trained before the checkpoint
            if step > total:
                break
            flat = [p for i in pack for p in train_q[i][0]]
            logits = scorer.logits(flat)
            loss = group_loss(
                torch, logits, [len(train_q[i][0]) for i in pack], [train_q[i][1] for i in pack]
            )
            loss.backward()
            torch.nn.utils.clip_grad_norm_(scorer.model.parameters(), 1.0)
            opt.step()
            sched.step()
            opt.zero_grad(set_to_none=True)
            state["step"] = step
            pairs_seen += len(flat)
            if step % 20 == 0:
                el = time.time() - started
                log(
                    run_dir,
                    event="step",
                    step=step,
                    total=total,
                    epoch=epoch,
                    loss=round(loss.item(), 4),
                    lr=sched.get_last_lr()[0],
                    pairs_per_s=round(pairs_seen / el, 1),
                )
            if max_steps:
                continue
            if step % eval_every == 0 or step == total:
                acc = accuracy(scorer, dev_q, budget * 2)
                log(run_dir, event="eval", step=step, dev_acc=round(acc, 4))
                if acc > state["best"]:
                    state.update(best=acc, best_step=step)
                    scorer.model.save_pretrained(f"{run_dir}/best")
                    scorer.tok.save_pretrained(f"{run_dir}/best")
                save_ckpt(ckpt, scorer, opt, sched, state)
            elif step % CKPT_EVERY == 0:
                save_ckpt(ckpt, scorer, opt, sched, state)
    el = time.time() - started
    summary = dict(
        state,
        seconds=round(el),
        pairs_per_s=round(pairs_seen / max(el, 1e-9), 1),
        total_steps=sum(len(o) for o in orders),
        total_pairs=sum(len(q[0]) for q in train_q) * epochs,
    )
    log(run_dir, event="done" if not max_steps else "bench", **summary)
    volume.commit()
    return summary


@app.function(gpu=GPU, volumes={"/vol": volume}, timeout=3 * 3600)
def predict_remote(name, model_id=None, scorer_kind="head", budget=256):
    """Raw per-option logits for every record of the evaluation partitions."""
    sys.path.insert(0, "/app")
    import torch
    from crossenc import api_request, pairs, request_key

    run_dir = f"/vol/runs/{name}"
    os.makedirs(run_dir, exist_ok=True)
    path = f"{run_dir}/best" if scorer_kind == "head" else None
    revision = NLI_REVISION if model_id == NLI else (BASE_REVISION if not model_id else None)
    scorer = Scorer(model_id or BASE, scorer_kind, revision=revision, path=path)
    json.dump(
        {"model": model_id or BASE, "revision": revision, "scorer": scorer_kind, "weights": path},
        open(f"{run_dir}/predict.json", "w"),
    )
    scorer.model.eval()
    out = open(f"{run_dir}/logits.jsonl", "w")
    count = 0
    with torch.no_grad():
        for suite, splits in SUITES.items():
            for split in splits:
                for record in load(suite, split):
                    request = api_request(record)
                    qs = pairs(request)
                    flat = [p for _, _, _, pp in qs for p in pp]
                    lg = (
                        scorer.logits(flat).tolist()
                        if len(flat) <= budget
                        else sum(
                            (
                                scorer.logits(flat[i : i + budget]).tolist()
                                for i in range(0, len(flat), budget)
                            ),
                            [],
                        )
                    )
                    per, start = {}, 0
                    for qid, _, _, pp in qs:
                        per[qid] = lg[start : start + len(pp)]
                        start += len(pp)
                    out.write(
                        json.dumps(
                            {
                                "key": request_key(request),
                                "suite": suite,
                                "split": split,
                                "id": record["_meta"]["id"],
                                "logits": per,
                            }
                        )
                        + "\n"
                    )
                    count += 1
    out.close()
    volume.commit()
    return count


@app.local_entrypoint()
def bench(steps: int = 40, budget: int = 128):
    state = train_remote.remote(f"bench-{int(time.time())}", budget=budget, max_steps=steps)
    print(state)


@app.local_entrypoint()
def train(name: str, lr: float = 2e-5, epochs: int = 2, seed: int = 1, budget: int = 128):
    print(train_remote.remote(name, lr=lr, epochs=epochs, seed=seed, budget=budget))


@app.local_entrypoint()
def predict(name: str, model: str = "", scorer: str = "head"):
    print(predict_remote.remote(name, model_id=model or None, scorer_kind=scorer), "records")
