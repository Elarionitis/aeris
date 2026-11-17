"""Tests for the public-deployment guards: rate limiting and answer caching."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.agents.cache import AnswerCache
from app.api import orchestrator as orchestrator_api
from app.core.ratelimit import FixedWindowLimiter, client_key
from app.main import app


# --------------------------------------------------------------------------
# Limiter
# --------------------------------------------------------------------------


def test_allows_up_to_capacity_then_blocks():
    limiter = FixedWindowLimiter(capacity=3, window_seconds=60)
    assert [limiter.check("a", now=0.0).allowed for _ in range(3)] == [True, True, True]

    blocked = limiter.check("a", now=0.0)
    assert blocked.allowed is False
    assert blocked.remaining == 0
    assert blocked.retry_after > 0


def test_remaining_counts_down():
    limiter = FixedWindowLimiter(capacity=3, window_seconds=60)
    assert [limiter.check("a", now=0.0).remaining for _ in range(3)] == [2, 1, 0]


def test_keys_are_independent():
    limiter = FixedWindowLimiter(capacity=1, window_seconds=60)
    assert limiter.check("a", now=0.0).allowed
    assert limiter.check("b", now=0.0).allowed
    assert not limiter.check("a", now=0.0).allowed


def test_window_resets():
    limiter = FixedWindowLimiter(capacity=2, window_seconds=60)
    limiter.check("a", now=0.0)
    limiter.check("a", now=0.0)
    assert not limiter.check("a", now=30.0).allowed
    # A fresh window admits the caller again.
    assert limiter.check("a", now=61.0).allowed


def test_rejects_nonsense_configuration():
    with pytest.raises(ValueError):
        FixedWindowLimiter(capacity=0, window_seconds=60)
    with pytest.raises(ValueError):
        FixedWindowLimiter(capacity=5, window_seconds=0)


def test_client_key_prefers_the_proxy_header():
    class FakeClient:
        host = "10.0.0.1"

    class FakeRequest:
        def __init__(self, headers):
            self.headers = headers
            self.client = FakeClient()

    # Render terminates TLS at a proxy, so the direct peer is never the user.
    assert client_key(FakeRequest({"x-forwarded-for": "203.0.113.9, 10.0.0.1"})) == "203.0.113.9"
    assert client_key(FakeRequest({})) == "10.0.0.1"


# --------------------------------------------------------------------------
# Cache
# --------------------------------------------------------------------------


def test_cache_roundtrip_and_miss():
    cache = AnswerCache(max_entries=4, ttl_seconds=900)
    key = cache.key("Why is BTM polluted?", "BTM", "en")
    assert cache.get(key) is None

    cache.set(key, {"answer": "because industry"})
    assert cache.get(key)["answer"] == "because industry"


def test_cache_key_normalises_whitespace_and_case():
    cache = AnswerCache()
    assert cache.key("  Why   is BTM  bad? ", "BTM", "en") == cache.key("why is btm bad?", "BTM", "en")
    # Ward and language stay part of the identity.
    assert cache.key("q", "BTM", "en") != cache.key("q", "HSR", "en")
    assert cache.key("q", "BTM", "en") != cache.key("q", "BTM", "kn")


def test_cache_evicts_least_recently_used():
    cache = AnswerCache(max_entries=2, ttl_seconds=900)
    cache.set("a", {"answer": "a"})
    cache.set("b", {"answer": "b"})
    cache.get("a")                      # 'a' becomes most recently used
    cache.set("c", {"answer": "c"})     # evicts 'b'

    assert cache.get("a") is not None
    assert cache.get("b") is None
    assert cache.get("c") is not None


def test_zero_ttl_disables_the_cache():
    cache = AnswerCache(max_entries=4, ttl_seconds=0)
    cache.set("a", {"answer": "a"})
    assert cache.get("a") is None


def test_cached_payload_is_copied_not_shared():
    cache = AnswerCache()
    cache.set("a", {"answer": "original"})
    fetched = cache.get("a")
    fetched["answer"] = "mutated"
    assert cache.get("a")["answer"] == "original"


# --------------------------------------------------------------------------
# Endpoint
# --------------------------------------------------------------------------


@pytest.fixture
def limited_client(monkeypatch):
    """A client whose orchestrator endpoint allows only two questions."""
    orchestrator_api.reset_limiter()
    # One shared instance: a factory would reset the count on every request.
    limiter = FixedWindowLimiter(capacity=2, window_seconds=3600)
    monkeypatch.setattr(orchestrator_api, "get_limiter", lambda: limiter)
    with TestClient(app) as client:
        yield client
    orchestrator_api.reset_limiter()


def test_endpoint_returns_429_past_the_limit(limited_client):
    body = {"question": "Where should enforcement teams go first?"}
    assert limited_client.post("/orchestrator/query", json=body).status_code == 200
    assert limited_client.post("/orchestrator/query", json=body).status_code == 200

    blocked = limited_client.post("/orchestrator/query", json=body)
    assert blocked.status_code == 429
    assert blocked.headers.get("retry-after")
    assert "Rate limit" in blocked.json()["detail"]


def test_endpoint_reports_remaining_budget(limited_client):
    first = limited_client.post("/orchestrator/query", json={"question": "Give me a city overview"})
    assert first.headers["x-ratelimit-limit"] == "2"
    assert first.headers["x-ratelimit-remaining"] == "1"


def test_responses_report_whether_they_were_cached(limited_client):
    payload = limited_client.post(
        "/orchestrator/query", json={"question": "Give me a city overview"}
    ).json()
    # The deterministic path is never cached, so this is always a fresh answer.
    assert payload["cached"] is False
