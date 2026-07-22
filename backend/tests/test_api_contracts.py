from __future__ import annotations

import pandas as pd
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field

from app.main import app


class WardContract(BaseModel):
    ward_id: str
    ward_name: str
    aqi: int
    band: str
    latitude: float
    longitude: float
    geometry: dict


class ForecastItem(BaseModel):
    horizon_hours: int
    prediction: float
    lower: float
    upper: float


class ForecastContract(BaseModel):
    ward_id: str
    forecast: list[ForecastItem]


class AttributionContract(BaseModel):
    ward_id: str
    timestamp: str
    breakdown: dict[str, float]
    confidence_score: float = Field(ge=0.0, le=1.0)
    method: str


class EnrichmentContract(BaseModel):
    ward_id: str
    timestamp: str
    breakdown: dict[str, float]
    confidence_score: float = Field(ge=0.0, le=1.0)
    method: str


class AdvisoryContract(BaseModel):
    ward_id: str
    language: str
    aqi_band: str
    vulnerability_index: float
    advisory: str
    vulnerability_flags: dict[str, bool]
    delivery_channels: list[str]
    disclaimer: str


class PriorityItem(BaseModel):
    ward_id: str
    ward_name: str
    aqi: int
    aqi_band: str
    score: float
    dominant_source: str
    source_density_nearby: float
    source_coordinates: list[dict]
    recommendation: str


class PriorityQueueContract(BaseModel):
    items: list[PriorityItem]
    disclaimer: str


def test_api_contracts(monkeypatch):
    from app.api import routes as api_routes

    monkeypatch.setattr(api_routes, "load_forecast_artifact", lambda: {"model": None, "feature_columns": [], "horizons": [1], "train_frame": pd.DataFrame()})
    monkeypatch.setattr(api_routes, "recursive_forecast", lambda artifact, ward_frame: ([101.0], [95.0], [107.0]))

    class FakeAttribution:
        confidence_score = 0.82
        method = "nnls_regression"

        def predict_breakdown(self, frame):
            return {"traffic": 30.0, "construction": 20.0, "industrial": 40.0, "other": 10.0}

    monkeypatch.setattr(api_routes, "load_attribution_model", lambda: FakeAttribution())
    monkeypatch.setattr(api_routes, "generate_advisory_response", lambda ward_id, language='en': {
        "ward_id": ward_id,
        "language": language,
        "aqi_band": "Poor",
        "vulnerability_index": 0.72,
        "advisory": "Reduce outdoor exposure.",
        "vulnerability_flags": {"near_school": True, "near_hospital": True, "elderly_population_high": False},
        "delivery_channels": ["app_push", "led_display", "ivr_script"],
        "disclaimer": "Review before dispatch.",
    })
    monkeypatch.setattr(api_routes, "priority_queue_response", lambda limit=10: {
        "items": [
            {
                "ward_id": "BTM",
                "ward_name": "BTM",
                "aqi": 168,
                "aqi_band": "Poor",
                "score": 123.4,
                "dominant_source": "industrial",
                "source_density_nearby": 2.0,
                "source_coordinates": [{"source_name": "Stack cluster A", "latitude": 12.9, "longitude": 77.6}],
                "recommendation": "Inspect BTM",
            }
        ],
        "disclaimer": "Mock registry used for MVP prioritization.",
    })

    client = TestClient(app)
    wards = client.get("/wards").json()
    WardContract.model_validate(wards[0])

    forecast = client.post("/forecast/BTM", json={"history": [{"ward_id": "BTM", "timestamp": "2026-07-20T00:00:00Z", "aqi": 100}] * 30}).json()
    ForecastContract.model_validate(forecast)

    attribution = client.get("/attribution/BTM").json()
    AttributionContract.model_validate(attribution)

    queue = client.get("/enforcement/priority-queue").json()
    PriorityQueueContract.model_validate(queue)

    advisory = client.get("/advisory/BTM?lang=kn").json()
    AdvisoryContract.model_validate(advisory)
