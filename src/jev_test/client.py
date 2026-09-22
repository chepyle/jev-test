"""Minimal client for OpenRouter's documented System One endpoint."""

import asyncio
import json
import math
import random
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import httpx

DEFAULT_ENDPOINT = "https://openrouter.ai/api/v1/systemone"
DEFAULT_MODEL = "~typesafe/jev-latest"
RETRYABLE = {408, 429, 500, 502, 503, 504}


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


def retry_delay(header: str | None, attempt: int) -> float:
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
    return min(2**attempt + random.uniform(0, 0.5), 60)


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
                await asyncio.sleep(retry_delay(response.headers.get("retry-after"), attempt))
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
                }
                hint = hints.get(response.status_code, "see OpenRouter request logs")
                raise InferenceError(f"HTTP {response.status_code}: {hint}", attempt + 1)
            try:
                body = json.loads(response.content, parse_constant=reject_nonfinite)
            except ValueError as error:
                raise InferenceError("Non-JSON response from System One", attempt + 1) from error
            if not isinstance(body, dict) or "error" in body:
                raise InferenceError("System One returned an API error envelope", attempt + 1)
            return Result(body, attempt + 1)
        raise AssertionError("unreachable")
