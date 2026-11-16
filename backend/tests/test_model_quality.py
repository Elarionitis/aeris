from __future__ import annotations

import time

import numpy as np
import pandas as pd

from app.api import routes as api_routes
from app.main import app
from app.models.attribution import fit_attribution_model
from app.models.forecasting import evaluate_forecast, train_forecast_model

from app.domain.wards import WARD_STATE


def _forecast_fixture():
    rows = []
    wards = WARD_STATE["ward_id"].tolist()
    timestamps = pd.date_range("2026-01-01", periods=240, freq="h", tz="UTC")
    for ward_index, ward_id in enumerate(wards):
        for index, timestamp in enumerate(timestamps):
            hour = timestamp.hour
            traffic = 0.6 + 0.05 * np.sin(index / 9)
            construction = 0.4 + 0.03 * np.cos(index / 14)
            industrial = 0.5 + 0.02 * ward_index
            thermal = 0.1 if index % 48 < 4 else 0.0
            aqi = 70 + 18 * np.sin(2 * np.pi * hour / 24) + 12 * traffic + 10 * construction + 8 * industrial + 6 * thermal
            rows.append(
                {
                    "ward_id": ward_id,
                    "timestamp": timestamp,
                    "aqi": aqi,
                    "wind_speed": 2.0 + (index % 5) * 0.2,
                    "wind_direction": 120,
                    "temperature": 30.0 + np.sin(index / 18),
                    "humidity": 60.0,
                    "traffic_density_index": traffic,
                    "construction_permit_count": construction,
                    "industrial_stack_count": industrial,
                    "thermal_anomaly_count_24h": thermal,
                }
            )
    return pd.DataFrame(rows)


def test_forecast_beats_persistence_by_margin(tmp_path, monkeypatch):
    frame = _forecast_fixture()
    monkeypatch.setattr("app.models.forecasting.ARTIFACT_DIR", tmp_path)
    monkeypatch.setattr("app.models.forecasting.MODEL_PATH", tmp_path / "forecast_model.pkl")
    report = evaluate_forecast(frame)
    comparison = report["comparison_table"]
    assert not comparison.empty
    baseline = comparison["baseline_rmse"].mean()
    model = comparison["model_rmse"].mean()
    assert model <= baseline * 0.9


def test_attribution_r2_threshold(tmp_path, monkeypatch):
    frame = _forecast_fixture().copy()
    frame["traffic_density_index"] = np.linspace(1.0, 10.0, len(frame))
    frame["construction_permit_count"] = np.linspace(0.5, 6.0, len(frame))
    frame["industrial_stack_count"] = np.linspace(0.2, 8.0, len(frame))
    frame["thermal_anomaly_count_24h"] = np.linspace(0.1, 3.0, len(frame))
    frame["aqi"] = (
        20
        + 2.5 * frame["traffic_density_index"]
        + 3.2 * frame["construction_permit_count"]
        + 4.1 * frame["industrial_stack_count"]
        + 1.7 * frame["thermal_anomaly_count_24h"]
    )
    monkeypatch.setattr("app.models.attribution.ARTIFACT_DIR", tmp_path)
    monkeypatch.setattr("app.models.attribution.ATTRIBUTION_PATH", tmp_path / "attribution_model.pkl")
    model = fit_attribution_model(frame)
    assert model.confidence_score >= 0.8


def test_smoke_pipeline_end_to_end(tmp_path, monkeypatch):
    frame = _forecast_fixture()
    forecast_artifact = train_forecast_model(frame)
    attribution_model = fit_attribution_model(frame)
    monkeypatch.setattr(api_routes, "load_forecast_artifact", lambda: forecast_artifact)
    monkeypatch.setattr(api_routes, "load_attribution_model", lambda: attribution_model)

    from fastapi.testclient import TestClient

    client = TestClient(app)
    wards = client.get("/wards").json()
    start = time.perf_counter()
    for ward in wards:
        history_frame = frame.loc[frame["ward_id"] == ward["ward_id"]].tail(36).copy()
        history_frame["timestamp"] = history_frame["timestamp"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        history = history_frame.to_dict(orient="records")
        forecast = client.post(f"/forecast/{ward['ward_id']}", json={"history": history}).json()
        attribution = client.get(f"/attribution/{ward['ward_id']}").json()
        advisory = client.get(f"/advisory/{ward['ward_id']}?lang=kn").json()
        assert forecast["forecast"]
        assert attribution["breakdown"]
        assert advisory["advisory"]
    # Eight wards x (72-step rollout + attribution + advisory) must stay well
    # inside a demo-friendly budget.
    assert time.perf_counter() - start < 5
