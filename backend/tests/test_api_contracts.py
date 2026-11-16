"""Contract tests over the real application, with real trained models.

The app bootstraps its own model artifacts on startup, so these tests exercise
the production code path rather than monkeypatched stand-ins.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.schemas import (
    AdvisoryResponse,
    AttributionResponse,
    ForecastResponse,
    HealthResponse,
    OrchestratorResponse,
    PriorityQueueResponse,
    ToolCatalogueResponse,
    WardResponse,
)
from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_root_and_health(client):
    assert client.get("/").status_code == 200

    health = HealthResponse.model_validate(client.get("/health").json())
    assert health.status == "ok"
    assert health.models["forecast_model"] == "ready"
    assert health.models["attribution_model"] == "ready"


def test_meta_exposes_band_scale(client):
    meta = client.get("/meta").json()
    labels = [band["label"] for band in meta["band_scale"]]
    assert labels == ["Good", "Satisfactory", "Moderate", "Poor", "Very Poor", "Severe"]
    assert {language["code"] for language in meta["languages"]} == {"en", "kn", "ta", "hi"}


def test_wards_contract(client):
    wards = client.get("/wards").json()
    assert wards
    for ward in wards:
        WardResponse.model_validate(ward)


def test_forecast_get_contract(client):
    payload = ForecastResponse.model_validate(client.get("/forecast/BTM?hours=24").json())
    assert payload.source == "baseline_history"
    assert len(payload.forecast) == 24
    assert [point.horizon_hours for point in payload.forecast] == list(range(1, 25))
    for point in payload.forecast:
        assert point.lower <= point.prediction <= point.upper
        assert point.prediction >= 0


def test_forecast_post_contract(client):
    history = [
        {
            "ward_id": "BTM",
            "timestamp": f"2026-07-20T{hour:02d}:00:00Z",
            "aqi": 150 + hour,
            "wind_speed": 2.0,
            "wind_direction": 120,
            "temperature": 29.0,
            "humidity": 60.0,
            "traffic_density_index": 0.8,
            "construction_permit_count": 2.0,
            "industrial_stack_count": 1.0,
            "thermal_anomaly_count_24h": 0.0,
        }
        for hour in range(24)
    ]
    response = client.post("/forecast/BTM", json={"history": history, "steps": 6})
    payload = ForecastResponse.model_validate(response.json())
    assert payload.source == "request_history"
    assert len(payload.forecast) == 6


def test_forecast_rejects_bad_history(client):
    assert client.post("/forecast/BTM", json={"history": []}).status_code == 422
    assert client.post("/forecast/BTM", json={"history": [{"ward_id": "BTM"}]}).status_code == 422
    assert client.post("/forecast/BTM", json={"history": [{"ward_id": "HSR", "timestamp": "2026-07-20T00:00:00Z", "aqi": 100}]}).status_code == 404


def test_attribution_contract_and_overrides(client):
    payload = AttributionResponse.model_validate(client.get("/attribution/BTM").json())
    assert pytest.approx(sum(payload.breakdown.values()), abs=0.05) == 100.0

    # Zeroing every source signal leaves nothing attributable but background.
    zeroed = client.get(
        "/attribution/BTM",
        params={
            "traffic_density_index": 0,
            "construction_permit_count": 0,
            "industrial_stack_count": 0,
            "thermal_anomaly_count_24h": 0,
        },
    ).json()
    assert zeroed["breakdown"]["other"] == pytest.approx(100.0, abs=0.05)


def test_enforcement_contract(client):
    payload = PriorityQueueResponse.model_validate(
        client.get("/enforcement/priority-queue?limit=5").json()
    )
    assert len(payload.items) == 5
    scores = [item.score for item in payload.items]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.parametrize("language", ["en", "kn", "ta", "hi"])
def test_advisory_contract_every_language(client, language):
    payload = AdvisoryResponse.model_validate(
        client.get(f"/advisory/BTM?lang={language}").json()
    )
    assert payload.language == language
    assert payload.advisory.strip()
    assert 0.0 <= payload.vulnerability_index <= 1.0


def test_unknown_ward_returns_404(client):
    for path in ("/forecast/Nowhere", "/attribution/Nowhere", "/advisory/Nowhere"):
        assert client.get(path).status_code == 404


def test_orchestrator_tool_catalogue(client):
    payload = ToolCatalogueResponse.model_validate(client.get("/orchestrator/tools").json())
    names = {tool.name for tool in payload.tools}
    assert {"forecast_ward_aqi", "attribute_ward_sources", "rank_enforcement_priority"} <= names
    for tool in payload.tools:
        assert tool.description
        assert tool.parameters


def test_orchestrator_query_contract(client):
    response = client.post(
        "/orchestrator/query",
        json={"question": "Why is BTM polluted and will it get worse?", "ward_id": "BTM"},
    )
    payload = OrchestratorResponse.model_validate(response.json())
    assert payload.answer.strip()
    assert payload.trace
    assert {entry.tool for entry in payload.trace} <= {
        "list_wards", "forecast_ward_aqi", "attribute_ward_sources", "rank_enforcement_priority",
    }


def test_orchestrator_rejects_empty_question(client):
    assert client.post("/orchestrator/query", json={"question": "hi"}).status_code == 422
