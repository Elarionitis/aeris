"""TTL cache for orchestrator answers.

On a public demo a handful of prompts, chiefly the suggested ones in the
dashboard, account for most traffic. Serving those from memory keeps provider
spend roughly flat no matter how many people click.

Only successful LLM answers are cached. A deterministic fallback answer is
cheap to recompute and reflects a degraded state, so caching one would keep
serving the degraded answer after the provider recovered.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)


class AnswerCache:
    """Bounded, TTL-expiring, least-recently-used cache."""

    def __init__(self, max_entries: int = 256, ttl_seconds: int = 900) -> None:
        self.max_entries = max(int(max_entries), 1)
        self.ttl_seconds = max(int(ttl_seconds), 0)
        self._lock = threading.Lock()
        self._entries: OrderedDict[str, tuple[float, dict[str, Any]]] = OrderedDict()
        self.hits = 0
        self.misses = 0

    @staticmethod
    def key(question: str, ward_id: str | None, language: str) -> str:
        """Normalise so trivial phrasing differences share one entry."""
        normalised = " ".join(str(question).split()).casefold()
        return f"{normalised}|{ward_id or ''}|{language or 'en'}"

    def get(self, key: str) -> dict[str, Any] | None:
        if self.ttl_seconds <= 0:
            return None
        now = time.monotonic()
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                self.misses += 1
                return None
            stored_at, payload = entry
            if now - stored_at > self.ttl_seconds:
                del self._entries[key]
                self.misses += 1
                return None
            self._entries.move_to_end(key)
            self.hits += 1
            return dict(payload)

    def set(self, key: str, payload: dict[str, Any]) -> None:
        if self.ttl_seconds <= 0:
            return
        with self._lock:
            self._entries[key] = (time.monotonic(), dict(payload))
            self._entries.move_to_end(key)
            while len(self._entries) > self.max_entries:
                self._entries.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self.hits = self.misses = 0

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {
                "entries": len(self._entries),
                "hits": self.hits,
                "misses": self.misses,
                "max_entries": self.max_entries,
                "ttl_seconds": self.ttl_seconds,
            }
