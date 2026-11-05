"""Serve Base Labs' elephant-1 as a System One endpoint on Modal.

elephant-1 (huggingface.co/baselabs/elephant-1) is Qwen3.5-9B post-trained as a decision model.
The release is served by OneJev's `qev` runtime at a pinned commit plus the repo's own
`serve.patch`; `setup.sh` from the model repo installs both, so the image runs that script
unchanged on the card's image (pytorch 2.8.0, CUDA 12.8). One request per forward pass.

    uvx modal run elephant_bench/modal_app.py::download
    uvx modal run elephant_bench/modal_app.py::count_tokens --requests results/elephant/probe.jsonl
    uvx modal deploy elephant_bench/modal_app.py
    curl -H "Authorization: Bearer $LLM2JEV_API_KEY" https://<workspace>--jev-test-elephant-server-api.modal.run/v1/models

The bearer key is the existing Modal secret `llm2jev-serve-key`. The card states a 16,384 token
limit and that longer requests are refused, not truncated; the server returns those as HTTP 422
with the engine's message so the client can count them.
"""

import json
import os
import threading
import time

import modal

MODEL = "baselabs/elephant-1"
MODEL_REVISION = "c54a55c2d362a7e30ff30814d28e39054e954d58"
SERVED_MODEL = f"{MODEL}@{MODEL_REVISION[:7]}"
MODEL_DIR = f"/vol/{MODEL}@{MODEL_REVISION[:7]}"
GPU = "H100"
MAX_CONTAINERS = 4

image = (
    modal.Image.from_registry("pytorch/pytorch:2.8.0-cuda12.8-cudnn9-devel")
    .apt_install("git")
    .pip_install("huggingface_hub[hf_xet]", "fastapi[standard]")
    .run_commands(
        # setup.sh needs only itself, constraints.txt and serve.patch from the model repo.
        f'python -c "from huggingface_hub import snapshot_download as d; '
        f"d('{MODEL}', revision='{MODEL_REVISION}', local_dir='/opt/elephant-files', "
        f"allow_patterns=['setup.sh', 'constraints.txt', 'serve.patch'])\"",
        "mkdir -p /opt/runtime && bash /opt/elephant-files/setup.sh /opt/runtime",
    )
    # After the build steps, so their caches do not land in the volume mount path.
    .env({"HF_HOME": "/vol/hf", "HF_XET_HIGH_PERFORMANCE": "1", "PYTHONUNBUFFERED": "1"})
)
models = modal.Volume.from_name("jev-elephant-models", create_if_missing=True)
app = modal.App("jev-test-elephant", image=image)


@app.function(volumes={"/vol": models}, timeout=3600)
def download():
    from huggingface_hub import snapshot_download

    snapshot_download(MODEL, revision=MODEL_REVISION, local_dir=MODEL_DIR)
    models.commit()
    print(sorted(os.listdir(MODEL_DIR)))


def load():
    import torch
    from qev.engine import DecisionEngine

    return DecisionEngine(MODEL_DIR, device="cuda:0"), torch


def answer(engine, torch, payload):
    from qev.schema import SystemOneRequest

    request = SystemOneRequest(state=payload.get("state"), questions=payload["questions"])
    torch.cuda.synchronize()
    start = time.perf_counter()
    resp, _ = engine.decide(request)
    torch.cuda.synchronize()
    out = {
        "model": SERVED_MODEL,
        "answers": {k: a.model_dump() for k, a in resp.answers.items()},
        "usage": resp.usage.model_dump(),
        "timing": {"forward_ms": round(1000 * (time.perf_counter() - start), 2)},
    }
    return out


@app.function(gpu=GPU, volumes={"/vol": models}, timeout=3600)
def probe(payloads: list[dict]) -> list[dict]:
    """Per request: the response, or the engine's refusal text."""
    engine, torch = load()
    answer(engine, torch, payloads[0]) if payloads else None  # warm-up, not recorded
    rows = []
    for p in payloads:
        try:
            rows.append(answer(engine, torch, p))
        except ValueError as error:
            rows.append({"refused": str(error)})
    return rows


@app.local_entrypoint()
def count_tokens(requests: str, output: str = "results/elephant/probe.json"):
    """Run request payloads (one JSON object per line) and write responses or refusals."""
    with open(requests) as fh:
        rows = [json.loads(line) for line in fh]
    result = probe.remote(rows)
    os.makedirs(os.path.dirname(output), exist_ok=True)
    with open(output, "w") as fh:
        json.dump(result, fh)
    print("wrote", output, "refused:", sum("refused" in r for r in result), "of", len(result))


@app.cls(
    gpu=GPU,
    volumes={"/vol": models},
    secrets=[modal.Secret.from_name("llm2jev-serve-key")],
    timeout=24 * 3600,
    scaledown_window=5 * 60,
    max_containers=MAX_CONTAINERS,
)
@modal.concurrent(max_inputs=32, target_inputs=8)  # one GPU forward at a time; queue the rest
class Server:
    @modal.enter()
    def start(self):
        self.engine, self.torch = load()
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
            return {"object": "list", "data": [{"id": "elephant-1", "served": SERVED_MODEL}]}

        @web.post("/v1/systemone")
        def systemone(payload: dict, request: Request):
            authorize(request)
            with self.lock:
                try:
                    return answer(self.engine, self.torch, payload)
                except ValueError as error:
                    raise HTTPException(422, str(error)) from error

        return web
