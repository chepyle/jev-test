"""Serve Cloudflare's Clef-flash as a System One endpoint on Modal.

Clef-flash (huggingface.co/Cloudflare/clef-flash) is Qwen3.5-9B plus a joint schema head that
scores every option of every question from one prefill. We serve the release's own
`systemone` function (`joint_schema_model.py` at a pinned revision) with the versions its model
card was tested with (torch 2.11, transformers 5.10.2), one request per forward pass, plus
flash-linear-attention for Qwen3.5's Gated DeltaNet layers (`kernel_check` compares it with
transformers' torch fallback).

    uvx modal run clef_bench/modal_app.py::download
    uvx modal run clef_bench/modal_app.py::kernel_check \
        --payloads results/clef-flash/check-payloads.jsonl
    uvx modal deploy clef_bench/modal_app.py
    curl -H "Authorization: Bearer $LLM2JEV_API_KEY" https://<workspace>--jev-test-clef-flash-server-api.modal.run/v1/models

The bearer key is the existing Modal secret `llm2jev-serve-key` (LLM2JEV_API_KEY), reused so
no new secret had to be written. Each response carries `timing.forward_ms`, the
CUDA-synchronized time of `systemone` (tokenization through probabilities), excluding HTTP.
"""

import json
import os
import sys
import threading
import time

import modal

MODEL = "Cloudflare/clef-flash"
MODEL_REVISION = "17f0b0ad64efb65d273590632833508766b2aae6"
SERVED_MODEL = f"{MODEL}@{MODEL_REVISION[:7]}"
MODEL_DIR = f"/models/{MODEL}@{MODEL_REVISION[:7]}"
# The post gives Clef a 64k context; the release's encode_record defaults to 16,384 tokens and
# silently cuts the state to fit, which would truncate long LexGLUE documents below our cap.
MAX_LENGTH = 65536
GPU = "H100"
MAX_CONTAINERS = 4

base = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install(
        "torch==2.11.0",
        "torchvision==0.26.0",
        "transformers==5.10.2",
        "accelerate==1.15.0",
        "safetensors==0.7.0",
        "huggingface_hub[hf_xet]",
        "pillow",
        "fastapi[standard]",
    )
    .env({"HF_HOME": "/models/hf", "HF_XET_HIGH_PERFORMANCE": "1", "PYTHONUNBUFFERED": "1"})
)
image = base.pip_install("flash-linear-attention==0.5.2")
models = modal.Volume.from_name("jev-clef-models", create_if_missing=True)
app = modal.App("jev-test-clef-flash", image=image)


@app.function(volumes={"/models": models}, timeout=3600)
def download():
    from huggingface_hub import snapshot_download

    snapshot_download(MODEL, revision=MODEL_REVISION, local_dir=MODEL_DIR)
    models.commit()
    print(sorted(os.listdir(MODEL_DIR)))


def load():
    import torch

    sys.path.insert(0, MODEL_DIR)
    import joint_schema_model

    model, processor = joint_schema_model.load_release_model(MODEL_DIR, device="cuda")
    return joint_schema_model, model, processor, torch


def answer(jsm, model, processor, torch, payload):
    torch.cuda.synchronize()
    start = time.perf_counter()
    response = jsm.systemone(model, processor, payload, max_length=MAX_LENGTH)
    torch.cuda.synchronize()
    response["model"] = SERVED_MODEL
    response["timing"] = {"forward_ms": round(1000 * (time.perf_counter() - start), 2)}
    return response


def score(payloads):
    from transformers.models.qwen3_5 import modeling_qwen3_5

    jsm, model, processor, torch = load()
    answer(jsm, model, processor, torch, payloads[0])  # warm-up (Triton autotune), not recorded
    return {
        "fast_path": bool(modeling_qwen3_5.is_fast_path_available),
        "fla": modeling_qwen3_5.chunk_gated_delta_rule is not None,
        "responses": [answer(jsm, model, processor, torch, p) for p in payloads],
    }


@app.function(gpu=GPU, volumes={"/models": models}, timeout=3600)
def score_fla(payloads: list[dict]) -> dict:
    return score(payloads)


@app.function(gpu=GPU, volumes={"/models": models}, timeout=3600, image=base)
def score_torch(payloads: list[dict]) -> dict:
    return score(payloads)


@app.local_entrypoint()
def kernel_check(payloads: str, output: str = "results/clef-flash/kernel-check.json"):
    """The served path (flash-linear-attention) against transformers' torch fallback."""
    with open(payloads) as fh:
        rows = [{**json.loads(line), "model": "clef-flash"} for line in fh]
    fla, ref = score_fla.spawn(rows), score_torch.spawn(rows)
    result = {"payloads": payloads, "fla": fla.get(), "torch": ref.get()}
    os.makedirs(os.path.dirname(output), exist_ok=True)
    with open(output, "w") as fh:
        json.dump(result, fh)
    print("wrote", output)


@app.cls(
    gpu=GPU,
    volumes={"/models": models},
    secrets=[modal.Secret.from_name("llm2jev-serve-key")],
    timeout=24 * 3600,
    scaledown_window=5 * 60,
    max_containers=MAX_CONTAINERS,
)
@modal.concurrent(max_inputs=32, target_inputs=8)  # one GPU forward at a time; queue the rest
class Server:
    @modal.enter()
    def start(self):
        self.jsm, self.model, self.processor, self.torch = load()
        self.lock = threading.Lock()

    @modal.asgi_app()
    def api(self):
        from fastapi import FastAPI, HTTPException, Request

        web = FastAPI()
        expected = f"Bearer {os.environ['LLM2JEV_API_KEY']}"

        def authorize(request: Request):
            if request.headers.get("authorization") != expected:
                raise HTTPException(401, "missing or invalid API key")

        @web.get("/v1/models")
        def list_models(request: Request):
            authorize(request)
            return {"object": "list", "data": [{"id": "clef-flash", "served": SERVED_MODEL}]}

        @web.post("/v1/systemone")
        def systemone(payload: dict, request: Request):
            authorize(request)
            with self.lock:
                try:
                    return answer(self.jsm, self.model, self.processor, self.torch, payload)
                except ValueError as error:
                    raise HTTPException(422, str(error)) from error

        return web
