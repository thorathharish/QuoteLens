"""Resilient outbound HTTP for distributor APIs: timeout, bounded retry, circuit breaker.

A slow or failing distributor must never stall an analysis. Each request gets a 4 s timeout
and at most 2 retries (429/5xx/network errors, exponential backoff). After 5 consecutive
failures the provider's circuit opens for 60 s and calls fail fast, so the chain falls back
to cached data and records why.
"""

import asyncio
import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 4.0
RETRIES = 2
RETRYABLE = {429, 500, 502, 503, 504}


class CircuitOpenError(RuntimeError):
    pass


class CircuitBreaker:
    def __init__(self, name: str, threshold: int = 5, reset_seconds: float = 60.0) -> None:
        self.name = name
        self.threshold = threshold
        self.reset_seconds = reset_seconds
        self.failures = 0
        self.opened_at: float | None = None

    def check(self) -> None:
        if self.opened_at is None:
            return
        if time.monotonic() - self.opened_at >= self.reset_seconds:
            self.opened_at = None  # half-open: let one request through
            self.failures = self.threshold - 1
            return
        raise CircuitOpenError(f"{self.name} temporarily disabled after repeated failures")

    def success(self) -> None:
        self.failures = 0
        self.opened_at = None

    def failure(self) -> None:
        self.failures += 1
        if self.failures >= self.threshold and self.opened_at is None:
            self.opened_at = time.monotonic()
            logger.warning("Circuit opened for %s", self.name)


async def request(
    client: httpx.AsyncClient,
    breaker: CircuitBreaker,
    method: str,
    url: str,
    *,
    sleep: Any = asyncio.sleep,
    **kwargs: Any,
) -> httpx.Response:
    """Send with retries. 4xx other than 429 are returned (e.g. 404 = not found), not retried."""
    breaker.check()
    last_error: Exception | None = None
    for attempt in range(RETRIES + 1):
        try:
            response = await client.request(method, url, timeout=TIMEOUT_SECONDS, **kwargs)
        except httpx.TransportError as exc:
            last_error = exc
        else:
            if response.status_code not in RETRYABLE:
                breaker.success()
                return response
            last_error = httpx.HTTPStatusError(
                f"{breaker.name} returned {response.status_code}",
                request=response.request,
                response=response,
            )
        if attempt < RETRIES:
            await sleep(0.5 * 2**attempt)
    breaker.failure()
    assert last_error is not None
    raise last_error
