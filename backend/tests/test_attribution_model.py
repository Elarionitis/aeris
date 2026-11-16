import pandas as pd

from app.models.attribution import summarize_attribution


def test_summarize_attribution_returns_breakdown(tmp_path, monkeypatch):
    master_table = pd.DataFrame(
        {
            "ward_id": ["Ward A"] * 12,
            "timestamp": pd.date_range("2026-01-01", periods=12, freq="h", tz="UTC"),
            "aqi": [100, 102, 98, 105, 110, 108, 111, 115, 113, 117, 120, 118],
            "traffic_density_index": [0.6, 0.7, 0.9, 0.8, 0.75, 0.8, 0.85, 0.9, 0.8, 0.82, 0.88, 0.9],
            "construction_permit_count": [1, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3, 3],
            "industrial_stack_count": [0, 1, 1, 1, 1, 2, 2, 2, 2, 2, 2, 2],
            "thermal_anomaly_count_24h": [0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1],
        }
    )
    result = summarize_attribution(master_table, "Ward A")
    assert result["method"] == "nnls_regression"
    assert set(result["breakdown"]) == {"traffic", "construction", "industrial", "other"}
