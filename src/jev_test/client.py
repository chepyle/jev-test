"""Minimal clients for OpenRouter's System One and chat-completions endpoints."""

import asyncio
import json
import math
import random
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import httpx

from jev_test.chat import normalize_usage

DEFAULT_ENDPOINT = "https://openrouter.ai/api/v1/systemone"
CHAT_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "~typesafe/jev-latest"
RETRYABLE = {408, 429, 500, 502, 503, 504, 529}
# Throttle and overload responses back off from 30 s: short cooldowns waste attempts.
THROTTLED = {429, 529}
PROVIDER_NAME = re.compile(r"[A-Za-z0-9 ._-]{1,64}")


def reject_nonfinite(value: str) -> None:
    raise ValueError(f"Nonfinite JSON number: {value}")


class InferenceError(Exception):
    def __init__(self, message: str, attempts: int):
        super().__init__(message)
        self.attempts = attempts


@dataclass
class Result:
    body: dict
    attempts: int


def retry_delay(header: str | None, attempt: int, base: float = 1.0) -> float:
    if header:
        try:
            seconds = float(header)
            if math.isfinite(seconds):
                return max(0, seconds)
        except ValueError:
            try:
                date = parsedate_to_datetime(header)
                return max(0, (date - datetime.now(UTC)).total_seconds())
            except (ValueError, TypeError):
                pass
    delay = base * 2**attempt
    return min(delay * random.uniform(1.0, 1.3), max(60, base * 8))


def provider_name(response: httpx.Response) -> str | None:
    """The failing provider from OpenRouter's error envelope, if it is a short plain name.

    Only this field is kept: metadata.raw carries the upstream body, which is never logged."""
    try:
        name = response.json()["error"]["metadata"]["provider_name"]
    except (ValueError, KeyError, TypeError):
        return None
    return name if isinstance(name, str) and PROVIDER_NAME.fullmatch(name) else None


class SystemOneClient:
    def __init__(
        self,
        http: httpx.AsyncClient,
        api_key: str,
        *,
        endpoint: str = DEFAULT_ENDPOINT,
        retries: int = 4,
    ):
        self.http = http
        self.api_key = api_key
        self.endpoint = endpoint
        self.retries = retries

    async def predict(self, payload: dict) -> Result:
        for attempt in range(self.retries + 1):
            try:
                response = await self.http.post(
                    self.endpoint,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "X-OpenRouter-Title": "Jev LexGLUE benchmark",
                    },
                )
            except httpx.TransportError as error:
                if attempt == self.retries:
                    raise InferenceError(
                        f"Transport failure: {type(error).__name__}", attempt + 1
                    ) from error
                await asyncio.sleep(retry_delay(None, attempt))
                continue
            if response.status_code in RETRYABLE and attempt < self.retries:
                base = 30.0 if response.status_code in THROTTLED else 1.0
                await asyncio.sleep(retry_delay(response.headers.get("retry-after"), attempt, base))
                continue
            if response.is_error:
                # Never put request headers or arbitrary upstream bodies in logs.
                hints = {
                    401: "check OPENROUTER_API_KEY",
                    402: "check OpenRouter credits",
                    400: "check request/context size",
                    404: "check endpoint and model ID",
                    413: "reduce --max-chars",
                    429: "reduce --concurrency",
                    529: "provider overloaded",
                }
                hint = hints.get(response.status_code, "see OpenRouter request logs")
                provider = provider_name(response)
                source = f" (provider {provider})" if provider else ""
                raise InferenceError(f"HTTP {response.status_code}{source}: {hint}", attempt + 1)
            try:
                body = json.loads(response.content, parse_constant=reject_nonfinite)
            except ValueError as error:
                raise InferenceError("Non-JSON response from System One", attempt + 1) from error
            if not isinstance(body, dict) or "error" in body:
                raise InferenceError("System One returned an API error envelope", attempt + 1)
            return Result(self.transform(body), attempt + 1)
        raise AssertionError("unreachable")

    def transform(self, body: dict) -> dict:
        return body


class ChatClient(SystemOneClient):
    """Same transport and retry policy against /chat/completions."""

    def __init__(self, *args, endpoint: str = CHAT_ENDPOINT, **kwargs):
        super().__init__(*args, endpoint=endpoint, **kwargs)

    def transform(self, body: dict) -> dict:
        return normalize_usage(body)
