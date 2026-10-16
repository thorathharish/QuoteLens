"""Small in-process sliding-window rate limiter (per client IP) for costly endpoints.

Per instance only, which is enough with Cloud Run max-instances 3: its job is protecting
the Gemini credit from accidental loops, not abuse at scale.
"""

import time
from collections import defaultdict, deque

from fastapi import Request

from app.domain.errors import RateLimitedError


class RateLimiter:
    def __init__(self, limit: int, window_seconds: float) -> None:
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> None:
        now = time.monotonic()
        hits = self._hits[key]
        while hits and now - hits[0] > self.window:
            hits.popleft()
        if len(hits) >= self.limit:
            retry = int(self.window - (now - hits[0])) + 1
            raise RateLimitedError(
                f"Too many copilot questions; try again in {retry}s", {"retry_after_seconds": retry}
            )
        hits.append(now)


def client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
