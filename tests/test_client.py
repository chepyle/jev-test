import asyncio

import httpx
import pytest

from jev_test.client import DEFAULT_ENDPOINT, InferenceError, SystemOneClient, retry_delay


def predict(handler, retries=2):
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            return await SystemOneClient(
                http, "k", endpoint=DEFAULT_ENDPOINT, retries=retries
            ).predict({"model": "m"})

    return asyncio.run(go())


def overloaded(provider="TypeSafe", raw="upstream secret body"):
    return httpx.Response(
        529,
        headers={"retry-after": "0"},
        json={
            "error": {
                "code": 529,
                "message": "Overloaded",
                "metadata": {"provider_name": provider, "raw": raw},
            }
        },
    )


def test_529_is_retried_then_succeeds():
    calls = []

    def handler(request):
        calls.append(1)
        return overloaded() if len(calls) == 1 else httpx.Response(200, json={"model": "m"})

    result = predict(handler)
    assert result.attempts == 2 and len(calls) == 2


def test_exhausted_529_names_the_provider_but_never_the_raw_body():
    with pytest.raises(InferenceError) as info:
        predict(lambda request: overloaded(), retries=1)
    message = str(info.value)
    assert message == "HTTP 529 (provider TypeSafe): provider overloaded"
    assert "secret" not in message


@pytest.mark.parametrize("name", ["x" * 65, "Bad\nName", "<script>", 42, None])
def test_unusual_provider_names_are_dropped(name):
    with pytest.raises(InferenceError) as info:
        predict(lambda request: overloaded(provider=name), retries=0)
    assert str(info.value) == "HTTP 529: provider overloaded"


def test_throttle_backoff_starts_at_30_seconds_and_other_errors_at_1():
    for attempt in range(4):
        assert 30 * 2**attempt <= retry_delay(None, attempt, 30.0) <= 240
        assert 2**attempt <= retry_delay(None, attempt, 1.0) <= 60
    assert retry_delay("5", 3, 30.0) == 5  # an explicit retry-after wins
