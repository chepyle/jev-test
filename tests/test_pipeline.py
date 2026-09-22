import asyncio
import json

import httpx
import pytest
from conftest import fake_response

from jev_test.client import DEFAULT_ENDPOINT, DEFAULT_MODEL, InferenceError, SystemOneClient
from jev_test.report import write_report
from jev_test.runner import run_benchmark
from jev_test.storage import read_jsonl


def run(prepared, output, handler, **kwargs):
    return asyncio.run(
        run_benchmark(
            prepared,
            output,
            model=DEFAULT_MODEL,
            endpoint=DEFAULT_ENDPOINT,
            api_key="test-secret",
            transport=httpx.MockTransport(handler),
            **kwargs,
        )
    )


def test_end_to_end_all_tasks_resume_and_offline_report(prepared, tmp_path):
    requests = []

    def handler(request):
        assert str(request.url) == DEFAULT_ENDPOINT
        assert request.headers["Authorization"] == "Bearer test-secret"
        requests.append(request)
        return httpx.Response(200, json=fake_response(request))

    output = tmp_path / "run"
    report = run(prepared, output, handler)
    assert len(requests) == 14
    assert report["complete"]
    assert report["selected_tasks_aggregate"] is not None
    assert report["lexglue_aggregate"] is None  # A sample must never be called a full score.
    assert report["usage"]["reported_cost_usd"] == pytest.approx(0.014)
    assert all(task["successful"] == 2 for task in report["tasks"].values())
    run(prepared, output, handler, resume=True)
    assert len(requests) == 14
    assert write_report(output) == report
    assert "test-secret" not in "".join(p.read_text() for p in output.iterdir() if p.is_file())
    with pytest.raises(ValueError, match="settings changed"):
        run(prepared, output, handler, resume=True, threshold=0.6)
    assert len(requests) == 14


def test_errors_stop_and_explicit_retry_restores_complete_coverage(prepared, tmp_path):
    output = tmp_path / "run"
    report = run(prepared, output, lambda _: httpx.Response(401), concurrency=1)
    assert not report["complete"]
    assert report["selected_tasks_aggregate"] is None
    assert report["tasks"]["ecthr_a"]["failed"] == 1
    assert report["usage"]["http_attempts"] == 1
    report = run(
        prepared,
        output,
        lambda r: httpx.Response(200, json=fake_response(r)),
        resume=True,
        retry_failed=True,
    )
    assert report["complete"]
    assert len(read_jsonl(output / "predictions.jsonl")) == 15


def test_invalid_response_is_checkpointed_with_usage_and_never_scored(prepared, tmp_path):
    def handler(request):
        response = fake_response(request)
        response["answers"].pop("label_0")
        return httpx.Response(200, json=response)

    output = tmp_path / "run"
    report = run(prepared, output, handler, concurrency=1)
    assert report["tasks"]["ecthr_a"]["scores"] is None
    assert report["usage"]["reported_cost_usd"] == 0.001
    assert read_jsonl(output / "predictions.jsonl")[0]["status"] == "error"


def test_latest_alias_rollover_stops_run_and_suppresses_aggregate(prepared, tmp_path):
    count = 0

    def handler(request):
        nonlocal count
        count += 1
        return httpx.Response(200, json=fake_response(request, model=f"jev-version-{count}"))

    report = run(prepared, tmp_path / "run", handler, concurrency=1)
    assert count == 2
    assert report["mixed_models"]
    assert report["selected_tasks_aggregate"] is None


def test_dry_run_needs_no_key_and_makes_no_requests(prepared, tmp_path):
    def unexpected_request(_):
        pytest.fail("Dry run made an API call")

    output = tmp_path / "preview"
    result = asyncio.run(
        run_benchmark(
            prepared,
            output,
            model=DEFAULT_MODEL,
            endpoint=DEFAULT_ENDPOINT,
            dry_run=True,
            transport=httpx.MockTransport(unexpected_request),
        )
    )
    assert result["requests"] == 14
    assert not (output / "predictions.jsonl").exists()
    assert "gold" not in json.dumps(read_jsonl(output / "requests.jsonl"))


def test_truncated_checkpoint_tail_is_repaired_on_resume(prepared, tmp_path):
    output = tmp_path / "run"

    def handler(request):
        return httpx.Response(200, json=fake_response(request))

    run(prepared, output, handler)
    with (output / "predictions.jsonl").open("ab") as handle:
        handle.write(b'{"id": "interrupted')
    result = run(prepared, output, handler, resume=True)
    assert result["complete"]
    assert len(read_jsonl(output / "predictions.jsonl")) == 14


def test_429_retries_but_auth_failure_does_not():
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, headers={"retry-after": "0"})
        return httpx.Response(200, json={"answers": {}, "model": "fixture"})

    async def exercise():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            result = await SystemOneClient(http, "key").predict({})
            assert result.attempts == 2
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _: httpx.Response(402))
        ) as http:
            with pytest.raises(InferenceError, match="credits") as exc:
                await SystemOneClient(http, "key").predict({})
            assert exc.value.attempts == 1

    asyncio.run(exercise())
    assert calls == 2


@pytest.mark.parametrize("model", [None, 123, []])
def test_malformed_model_is_checkpointed_without_breaking_report(prepared, tmp_path, model):
    def handler(request):
        response = fake_response(request)
        response["model"] = model
        response["usage"] = None
        return httpx.Response(200, json=response)

    report = run(prepared, tmp_path / "run", handler, concurrency=1)
    assert report["tasks"]["ecthr_a"]["failed"] == 1
    assert report["resolved_models"] == []
    assert report["usage"]["reported_cost_usd"] is None


def test_nonfinite_json_is_rejected_without_poisoning_ledger(prepared, tmp_path):
    report = run(
        prepared,
        tmp_path / "run",
        lambda _: httpx.Response(
            200, content=b'{"model": "jev", "answers": {"label_0": {"noul": NaN}}}'
        ),
        concurrency=1,
    )
    assert report["tasks"]["ecthr_a"]["failed"] == 1
    assert report["selected_tasks_aggregate"] is None
