"""Serve LLM2Jev (github.com/Yinsongxu/LLM2Jev) as a System One endpoint on Modal.

LLM2Jev turns a stock chat model into a System One server without training: every
candidate of every question becomes one yes/no prompt, the server reads P(yes) from the
next-token logits of a zero-token SGLang prefill, and choice candidates are L1-normalized.
We serve its own `llm2jev-serve --backend sglang` at a pinned commit on the SGLang image
version its lockfile pins, with Qwen3.5-4B, the model its JevBench result used.

    uvx modal run llm2jev_bench/modal_app.py::download
    uvx modal run llm2jev_bench/modal_app.py::prefix_check \
        --payloads results/llm2jev/prefix-payloads.jsonl
    uvx modal deploy llm2jev_bench/modal_app.py
    curl -H "Authorization: Bearer $LLM2JEV_API_KEY" https://<workspace>--jev-test-llm2jev-api.modal.run/v1/models

The bearer key comes from the Modal secret `llm2jev-serve-key` (LLM2JEV_API_KEY), passed
to SGLang's own --api-key check, which also guards /v1/systemone.
"""

import json
import os
import re
import subprocess
import time

import modal

LLM2JEV_REPO = "https://github.com/Yinsongxu/LLM2Jev"
LLM2JEV_COMMIT = "a4aafa85e1aba95329db36e085373d1572ab6917"
SGLANG_IMAGE = "lmsysorg/sglang:v0.5.20-cu130"  # LLM2Jev's uv.lock pins sglang 0.5.20 on CUDA 13
MODEL = "Qwen/Qwen3.5-4B"
MODEL_REVISION = "851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a"
SERVED_NAME = "qwen3.5-4b"
MODEL_DIR = f"/models/{MODEL}@{MODEL_REVISION[:7]}"
GPU = "H100"
PORT = 30000
MAX_CONTAINERS = 2  # every request carries its whole document, so reuse never spans containers

image = (
    modal.Image.from_registry(SGLANG_IMAGE)
    .entrypoint([])
    # The SGLang image already carries LLM2Jev's runtime deps (fastapi, openai, uvicorn).
    .run_commands(
        f"python3 -m pip install --no-deps 'llm2jev @ git+{LLM2JEV_REPO}@{LLM2JEV_COMMIT}'"
    )
    .env({"HF_HOME": "/models/hf", "HF_XET_HIGH_PERFORMANCE": "1", "PYTHONUNBUFFERED": "1"})
)
models = modal.Volume.from_name("jev-llm2jev-models", create_if_missing=True)
app = modal.App("jev-test-llm2jev", image=image)


def serve_command(api_key: str | None, *extra: str) -> list[str]:
    # --skip-server-warmup: SGLang 0.5.20 gives a request without token_ids_logprob a []
    # placeholder and then calls .tolist() on it, killing the scheduler, whenever such a request
    # shares a batch with scoring requests. The only such request is SGLang's own startup warmup
    # (/generate, 8 tokens), and Modal routes traffic as soon as the port opens, so a burst at
    # cold start crashed three containers. With it skipped, every request is a scoring request.
    # --disable-overlap-schedule was the first, insufficient workaround; it stays so that all
    # results share one serving config.
    cmd = [
        "llm2jev-serve", "--backend", "sglang", "--model-path", MODEL_DIR,
        "--served-model-name", SERVED_NAME, "--host", "0.0.0.0", "--port", str(PORT),
        "--disable-overlap-schedule", "--skip-server-warmup", *extra,
    ]  # fmt: skip
    return cmd + (["--api-key", api_key] if api_key else [])


@app.function(volumes={"/models": models}, timeout=3600)
def download():
    from huggingface_hub import snapshot_download

    snapshot_download(MODEL, revision=MODEL_REVISION, local_dir=MODEL_DIR)
    models.commit()
    print(sorted(os.listdir(MODEL_DIR)))


@app.function(
    gpu=GPU,
    volumes={"/models": models},
    secrets=[modal.Secret.from_name("llm2jev-serve-key")],
    timeout=24 * 3600,
    scaledown_window=10 * 60,
    max_containers=MAX_CONTAINERS,
)
@modal.concurrent(max_inputs=64, target_inputs=24)  # scale out past ~24 in flight
@modal.web_server(port=PORT, startup_timeout=30 * 60)
def api():
    subprocess.Popen(serve_command(os.environ["LLM2JEV_API_KEY"]))


def wait_ready(proc, log_path, timeout=1800):
    import urllib.request

    start = time.time()
    while time.time() - start < timeout:
        if proc.poll() is not None:
            raise RuntimeError(open(log_path).read()[-4000:])
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=5)
            return time.time() - start
        except OSError:
            time.sleep(2)
    raise TimeoutError("server did not start")


def post(payload):
    import urllib.request

    req = urllib.request.Request(
        f"http://127.0.0.1:{PORT}/v1/systemone",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=900) as response:
        body = json.loads(response.read())
    return body, time.perf_counter() - t0


PREFILL = re.compile(r"Prefill batch.*?#new-token: (\d+), #cached-token: (\d+)")


@app.function(gpu=GPU, volumes={"/models": models}, timeout=3 * 3600)
def check_configs(payloads: list[dict], configs: dict[str, list[str]]) -> dict:
    """Serve each config in turn on one GPU and send it the same payloads one at a time.

    Returns every response, its latency, and the prefill token counts SGLang logged, so the
    caller can compare probabilities across configs and see how many tokens were reused."""
    out = {}
    for name, extra in configs.items():
        log_path = f"/tmp/{name}.log"
        with open(log_path, "w") as log:
            proc = subprocess.Popen(
                serve_command(None, *extra), stdout=log, stderr=subprocess.STDOUT
            )
        try:
            startup = wait_ready(proc, log_path)
            post(payloads[0])  # warm-up (kernels, graphs), not recorded
            subprocess.run(
                ["curl", "-s", "-X", "POST", f"http://127.0.0.1:{PORT}/flush_cache"], check=False
            )
            before = open(log_path).read()
            rows = []
            for payload in payloads:
                body, seconds = post(payload)
                rows.append({"response": body, "seconds": seconds})
            logged = open(log_path).read()[len(before) :]
            counts = [tuple(map(int, m)) for m in PREFILL.findall(logged)]
            out[name] = {
                "startup_s": startup,
                "rows": rows,
                "new_tokens": sum(n for n, _ in counts),
                "cached_tokens": sum(c for _, c in counts),
            }
            print(
                name,
                f"{sum(r['seconds'] for r in rows):.1f}s",
                out[name]["new_tokens"],
                out[name]["cached_tokens"],
            )
        finally:
            proc.terminate()
            proc.wait(timeout=120)
    return out


@app.local_entrypoint()
def prefix_check(
    payloads: str,
    output: str = "results/llm2jev/prefix-check.json",
    configs: str = "staged,reference",
):
    """Staged prefix reuse (the served config) against a reference with no prefix cache."""
    available = {
        "staged": [],
        "reference": ["--submission", "all", "--disable-radix-cache"],
        "extra_buffer": ["--mamba-scheduler-strategy", "extra_buffer"],
    }
    with open(payloads) as fh:
        rows = [json.loads(line) for line in fh]
    selected = {name: available[name] for name in configs.split(",")}
    result = check_configs.remote(rows, selected)
    os.makedirs(os.path.dirname(output), exist_ok=True)
    with open(output, "w") as fh:
        json.dump({"configs": selected, "results": result}, fh)
    print("wrote", output)
