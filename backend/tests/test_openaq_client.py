from datetime import datetime, timezone

import pandas as pd

from app.ingestion.openaq_client import OpenAQClient


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


class FakeSession:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def request(self, method, url, params=None, headers=None, timeout=None):
        self.calls.append((method, url, params))
        return self.responses.pop(0)


def test_openaq_fetch_paginates_and_caches(tmp_path, monkeypatch):
    monkeypatch.setattr("app.ingestion._base.time.sleep", lambda *_args, **_kwargs: None)
    responses = [
        FakeResponse(
            {
                "results": [
                    {"location": "BTM", "parameter": "pm25", "value": 42.0, "date": {"utc": "2026-07-20T00:00:00Z"}},
                    {"location": "BTM", "parameter": "no2", "value": 17.0, "date": {"utc": "2026-07-20T00:10:00Z"}},
                ]
            }
        )
    ]
    client = OpenAQClient(cache_root=tmp_path, session=FakeSession(responses))
    frame = client.fetch("2026-07-20", "2026-07-20", wards=["BTM"])

    assert list(frame.columns) == ["ward_id", "timestamp", "metric", "value", "source"]
    assert set(frame["metric"]) == {"pm25", "no2"}
    assert (tmp_path / "2026-07-20.parquet").exists()
