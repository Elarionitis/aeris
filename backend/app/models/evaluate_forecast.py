from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error

from app.models.forecasting import build_training_frame, load_forecast_artifact, time_based_split, train_forecast_model


def evaluate_and_plot(master_table: pd.DataFrame, output_dir: Path | None = None) -> dict[str, object]:
    output_dir = output_dir or Path(__file__).resolve().parent / "artifacts"
    output_dir.mkdir(parents=True, exist_ok=True)
    frame = build_training_frame(master_table)
    train_frame, test_frame = time_based_split(frame)
    artifact = train_forecast_model(master_table)
    model = artifact["model"]
    feature_columns = artifact["feature_columns"]
    predictions = model.predict(test_frame[feature_columns])

    comparison = []
    for index, horizon in enumerate(artifact["horizons"]):
        target = test_frame.groupby("ward_id")["aqi"].shift(-horizon).dropna()
        y_pred = pd.Series(predictions[: len(target), index], index=target.index)
        baseline = pd.Series([train_frame["aqi"].iloc[-1]] * len(target), index=target.index, dtype=float)
        comparison.append(
            {
                "horizon": horizon,
                "baseline_rmse": mean_squared_error(target, baseline, squared=False),
                "baseline_mae": mean_absolute_error(target, baseline),
                "model_rmse": mean_squared_error(target, y_pred, squared=False),
                "model_mae": mean_absolute_error(target, y_pred),
            }
        )

    sample_wards = list(test_frame["ward_id"].dropna().astype(str).unique()[:3])
    fig, axes = plt.subplots(len(sample_wards), 1, figsize=(10, 4 * max(len(sample_wards), 1)), sharex=False)
    if len(sample_wards) == 1:
        axes = [axes]
    for axis, ward_id in zip(axes, sample_wards):
        ward_frame = test_frame[test_frame["ward_id"].astype(str) == ward_id]
        axis.plot(ward_frame["timestamp"], ward_frame["aqi"], label="actual", linewidth=2)
        axis.plot(ward_frame["timestamp"], model.predict(ward_frame[feature_columns])[:, 0], label="predicted", linewidth=2)
        axis.set_title(ward_id)
        axis.legend()
    plot_path = output_dir / "forecast_vs_actual.png"
    fig.tight_layout()
    fig.savefig(plot_path, dpi=160)
    plt.close(fig)
    comparison_table = pd.DataFrame(comparison)
    comparison_table.to_csv(output_dir / "forecast_comparison.csv", index=False)
    return {"comparison_table": comparison_table, "plot_path": str(plot_path), "artifact_path": str(output_dir / "forecast_model.pkl")}
