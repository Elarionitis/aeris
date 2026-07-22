from __future__ import annotations

import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.multioutput import MultiOutputRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

try:
    from xgboost import XGBRegressor
except Exception:  # pragma: no cover
    XGBRegressor = None

try:
    from prophet import Prophet
except Exception:  # pragma: no cover
    Prophet = None


ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"
MODEL_PATH = ARTIFACT_DIR / "forecast_model.pkl"
FEATURE_COLUMNS = [
    "aqi_lag_1h",
    "aqi_lag_24h",
    "aqi_rolling_6h",
    "aqi_rolling_24h",
    "wind_speed",
    "wind_direction",
    "temperature",
    "humidity",
    "traffic_density_index",
    "construction_permit_count",
    "industrial_stack_count",
    "thermal_anomaly_count_24h",
    "hour_sin",
    "hour_cos",
    "dow_sin",
    "dow_cos",
]
TARGET_COLUMN = "aqi"
HORIZONS = [1, 3, 6, 12, 24, 48, 72]


def _ensure_artifacts_dir() -> Path:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    return ARTIFACT_DIR


def _coerce_dataframe(master_table: pd.DataFrame) -> pd.DataFrame:
    frame = master_table.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    frame = frame.sort_values(["ward_id", "timestamp"]).reset_index(drop=True)
    return frame


def build_training_frame(master_table: pd.DataFrame) -> pd.DataFrame:
    frame = _coerce_dataframe(master_table)
    grouped = frame.groupby("ward_id", sort=False)
    frame["aqi_lag_1h"] = grouped[TARGET_COLUMN].shift(1)
    frame["aqi_lag_24h"] = grouped[TARGET_COLUMN].shift(24)
    frame["aqi_rolling_6h"] = grouped[TARGET_COLUMN].transform(lambda s: s.shift(1).rolling(6, min_periods=1).mean())
    frame["aqi_rolling_24h"] = grouped[TARGET_COLUMN].transform(lambda s: s.shift(1).rolling(24, min_periods=1).mean())
    hour = frame["timestamp"].dt.hour
    dow = frame["timestamp"].dt.dayofweek
    frame["hour_sin"] = np.sin(2 * np.pi * hour / 24)
    frame["hour_cos"] = np.cos(2 * np.pi * hour / 24)
    frame["dow_sin"] = np.sin(2 * np.pi * dow / 7)
    frame["dow_cos"] = np.cos(2 * np.pi * dow / 7)
    frame = frame.dropna(subset=["aqi_lag_1h", "aqi_lag_24h"]) 
    return frame


def time_based_split(frame: pd.DataFrame, train_fraction: float = 0.8) -> tuple[pd.DataFrame, pd.DataFrame]:
    ordered = frame.sort_values("timestamp").reset_index(drop=True)
    split_index = max(int(len(ordered) * train_fraction), 1)
    return ordered.iloc[:split_index].copy(), ordered.iloc[split_index:].copy()


def _feature_matrix(frame: pd.DataFrame) -> pd.DataFrame:
    return frame[FEATURE_COLUMNS].astype(float)


def _train_multi_horizon_model(train_frame: pd.DataFrame):
    targets = {f"aqi_t+{h}h": train_frame.groupby("ward_id")[TARGET_COLUMN].shift(-h) for h in HORIZONS}
    model_frame = train_frame.copy()
    for name, series in targets.items():
        model_frame[name] = series
    model_frame = model_frame.dropna(subset=list(targets.keys()))
    features = _feature_matrix(model_frame)
    target_matrix = model_frame[[f"aqi_t+{h}h" for h in HORIZONS]]
    if XGBRegressor is not None:
        base = XGBRegressor(
            n_estimators=250,
            learning_rate=0.05,
            max_depth=5,
            subsample=0.9,
            colsample_bytree=0.8,
            objective="reg:squarederror",
            random_state=42,
        )
    else:
        base = HistGradientBoostingRegressor(random_state=42)
    return MultiOutputRegressor(base).fit(features, target_matrix), model_frame


def _train_prophet_models(train_frame: pd.DataFrame) -> dict[str, object]:
    if Prophet is None:
        return {}
    models: dict[str, object] = {}
    for ward_id, ward_frame in train_frame.groupby("ward_id"):
        if len(ward_frame) < 10:
            continue
        prophet_frame = ward_frame[["timestamp", TARGET_COLUMN]].rename(columns={"timestamp": "ds", TARGET_COLUMN: "y"})
        prophet_frame["ds"] = pd.to_datetime(prophet_frame["ds"], utc=True).dt.tz_convert(None)
        model = Prophet(daily_seasonality=True, weekly_seasonality=True, yearly_seasonality=False)
        model.fit(prophet_frame)
        models[str(ward_id)] = model
    return models


def train_forecast_model(master_table: pd.DataFrame) -> dict[str, object]:
    frame = build_training_frame(master_table)
    train_frame, test_frame = time_based_split(frame)
    model, fitted_frame = _train_multi_horizon_model(train_frame)
    prophet_models = _train_prophet_models(train_frame)
    artifact = {
        "model": model,
        "prophet_models": prophet_models,
        "feature_columns": FEATURE_COLUMNS,
        "horizons": HORIZONS,
        "train_frame": fitted_frame,
    }
    _ensure_artifacts_dir()
    with MODEL_PATH.open("wb") as handle:
        pickle.dump(artifact, handle)
    return artifact


def load_forecast_artifact(path: Path | None = None) -> dict[str, object]:
    model_path = path or MODEL_PATH
    with model_path.open("rb") as handle:
        return pickle.load(handle)


def persistence_forecast(series: pd.Series, horizons: Iterable[int] = HORIZONS) -> pd.DataFrame:
    last_value = float(series.iloc[-1])
    return pd.DataFrame({f"h{h}": [last_value] for h in horizons})


def recursive_forecast(artifact: dict[str, object], ward_frame: pd.DataFrame, steps: int = 72) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    model = artifact["model"]
    feature_columns = artifact["feature_columns"]
    history = ward_frame.sort_values("timestamp").copy().reset_index(drop=True)
    predictions = []
    lower = []
    upper = []
    residual_std = float(history[TARGET_COLUMN].diff().dropna().std() or 1.0)
    for step in range(1, steps + 1):
        latest = history.iloc[-1:].copy()
        latest["aqi_lag_1h"] = history[TARGET_COLUMN].iloc[-1]
        latest["aqi_lag_24h"] = history[TARGET_COLUMN].iloc[-24] if len(history) >= 24 else history[TARGET_COLUMN].iloc[-1]
        latest["aqi_rolling_6h"] = history[TARGET_COLUMN].tail(6).mean()
        latest["aqi_rolling_24h"] = history[TARGET_COLUMN].tail(24).mean()
        future_timestamp = pd.Timestamp(history["timestamp"].iloc[-1]) + pd.Timedelta(hours=1)
        latest["hour_sin"] = np.sin(2 * np.pi * future_timestamp.hour / 24)
        latest["hour_cos"] = np.cos(2 * np.pi * future_timestamp.hour / 24)
        latest["dow_sin"] = np.sin(2 * np.pi * future_timestamp.dayofweek / 7)
        latest["dow_cos"] = np.cos(2 * np.pi * future_timestamp.dayofweek / 7)
        latest = latest.reindex(columns=feature_columns, fill_value=0)
        predicted = float(model.predict(latest)[0][0])
        predictions.append(predicted)
        lower.append(predicted - 1.96 * residual_std)
        upper.append(predicted + 1.96 * residual_std)
        history = pd.concat([
            history,
            pd.DataFrame(
                {
                    "ward_id": [history["ward_id"].iloc[-1]],
                    "timestamp": [future_timestamp],
                    TARGET_COLUMN: [predicted],
                }
            ),
        ], ignore_index=True)
    return np.asarray(predictions), np.asarray(lower), np.asarray(upper)


def evaluate_forecast(master_table: pd.DataFrame) -> dict[str, object]:
    frame = build_training_frame(master_table)
    train_frame, test_frame = time_based_split(frame)
    artifact = train_forecast_model(master_table)
    model = artifact["model"]
    test_frame = test_frame.dropna(subset=FEATURE_COLUMNS)
    preds = model.predict(_feature_matrix(test_frame))
    comparison_rows = []
    horizon_names = [f"aqi_t+{h}h" for h in HORIZONS]
    for idx, horizon_name in enumerate(horizon_names):
        y_true = test_frame.groupby("ward_id")[TARGET_COLUMN].shift(-HORIZONS[idx]).dropna()
        if y_true.empty:
            continue
        y_pred = pd.Series(preds[:, idx][: len(y_true)], index=y_true.index)
        comparison_rows.append(
            {
                "horizon": horizon_name,
                "baseline_rmse": float(np.sqrt(mean_squared_error(y_true, pd.Series([train_frame[TARGET_COLUMN].iloc[-1]] * len(y_true), index=y_true.index, dtype=float)))),
                "baseline_mae": float(mean_absolute_error(y_true, pd.Series([train_frame[TARGET_COLUMN].iloc[-1]] * len(y_true), index=y_true.index, dtype=float))),
                "model_rmse": float(np.sqrt(mean_squared_error(y_true, y_pred))),
                "model_mae": float(mean_absolute_error(y_true, y_pred)),
            }
        )
    return {"comparison_table": pd.DataFrame(comparison_rows), "artifact_path": str(MODEL_PATH)}
