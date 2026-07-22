import pandas as pd

from app.models.forecasting import build_training_frame, evaluate_forecast


def _master_table():
    timestamps = pd.date_range("2026-01-01", periods=120, freq="H", tz="UTC")
    return pd.DataFrame(
        {
            "ward_id": ["Ward A"] * len(timestamps),
            "timestamp": timestamps,
            "aqi": range(120),
            "wind_speed": 2.0,
            "wind_direction": 120,
            "temperature": 30.0,
            "humidity": 60.0,
            "traffic_density_index": 0.8,
            "construction_permit_count": 2.0,
            "industrial_stack_count": 1.0,
            "thermal_anomaly_count_24h": 0.0,
        }
    )


def test_evaluate_forecast_writes_artifact(tmp_path, monkeypatch):
    monkeypatch.setattr("app.models.forecasting.ARTIFACT_DIR", tmp_path)
    monkeypatch.setattr("app.models.forecasting.MODEL_PATH", tmp_path / "forecast_model.pkl")
    result = evaluate_forecast(_master_table())
    assert "comparison_table" in result
    assert (tmp_path / "forecast_model.pkl").exists()
