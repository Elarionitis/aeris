"""In-memory fixed-window rate limiting.

The orchestrator endpoint spends money and provider quota on every call, so a
public deployment needs a ceiling on it. This limiter is deliberately
in-process: the service runs a single worker, so a shared store would add a
dependency without adding accuracy. Move to Redis before scaling past one
worker, because each worker would otherwise enforce its own separate budget.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from fastapi import Request

#: Entries are pruned once the map grows past this, so a stream of unique
#: client addresses cannot grow memory without bound.
_PRUNE_THRESHOLD = 2048


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    remaining: int
    retry_after: int
    limit: int


class FixedWindowLimiter:
    """Allow ``capacity`` requests per ``window_seconds`` per key.

    A fixed window can admit up to twice the capacity across a window
    boundary. That is an acceptable trade for a demo-protection limiter, and
    it keeps the implementation small enough to reason about.
    """

    def __init__(self, capacity: int, window_seconds: int) -> None:
        if capacity < 1:
            raise ValueError("capacity must be at least 1")
        if window_seconds < 1:
            raise ValueError("window_seconds must be at least 1")
        self.capacity = capacity
        self.window_seconds = window_seconds
        self._lock = threading.Lock()
        self._hits: dict[str, tuple[int, float]] = {}

    def _prune(self, now: float) -> None:
        expired = [key for key, (_, start) in self._hits.items() if now - start >= self.window_seconds]
        for key in expired:
            del self._hits[key]

    def check(self, key: str, now: float | None = None) -> RateLimitResult:
        """Count one request against ``key`` and say whether it is allowed."""
        now = time.monotonic() if now is None else now
        with self._lock:
            if len(self._hits) > _PRUNE_THRESHOLD:
                self._prune(now)

            count, window_start = self._hits.get(key, (0, now))
            if now - window_start >= self.window_seconds:
                count, window_start = 0, now

            if count >= self.capacity:
                retry_after = max(1, int(self.window_seconds - (now - window_start)) + 1)
                return RateLimitResult(False, 0, retry_after, self.capacity)

            self._hits[key] = (count + 1, window_start)
            return RateLimitResult(True, self.capacity - count - 1, 0, self.capacity)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


def client_key(request: Request) -> str:
    """Identify the caller, honouring the proxy header Render sets.

    Render, and every other managed host, terminates TLS at a proxy, so
    request.client.host is the proxy rather than the visitor. The left-most
    X-Forwarded-For entry is the original client. It is spoofable by a direct
    caller, which is tolerable here: the limiter protects a demo budget, it is
    not a security control.
    """
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    return request.client.host if request.client else "unknown"
