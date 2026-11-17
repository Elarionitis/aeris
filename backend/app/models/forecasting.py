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

from app.core.config import get_settings
from app.core.logging import get_logger

try:
    from xgboost import XGBRegressor
except Exception:  # pragma: no cover
    XGBRegressor = None

try:
    from prophet import Prophet
except Exception:  # pragma: no cover
    Prophet = None


logger = get_logger(__name__)

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
#: Default length of a recursive rollout, in hours.
DEFAULT_HORIZON_HOURS = 72


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
    dow = frame["timestamp"].dt.day_of_week
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


def _feature_matrix(frame: pd.DataFrame) -> np.ndarray:
    """Feature matrix in a fixed column order.

    Returned as a plain array so the fitted estimators carry no pandas feature
    names; the recursive rollout can then predict from a bare numpy row.
    """
    return frame.reindex(columns=FEATURE_COLUMNS).astype(float).to_numpy()


def _train_multi_horizon_model(train_frame: pd.DataFrame):
    targets = {f"aqi_t+{h}h": train_frame.groupby("ward_id")[TARGET_COLUMN].shift(-h) for h in HORIZONS}
    model_frame = train_frame.copy()
    for name, series in targets.items():
        model_frame[name] = series
    model_frame = model_frame.dropna(subset=list(targets.keys()))
    features = _feature_matrix(model_frame)
    target_matrix = model_frame[[f"aqi_t+{h}h" for h in HORIZONS]].astype(float).to_numpy()
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
    """Fit a per-ward Prophet model as an interpretable seasonality baseline.

    Prophet is not on the serving path -- ``recursive_forecast`` rolls the
    gradient-boosted model forward -- and fitting it per ward costs tens of
    seconds, so it stays off unless ``ENABLE_PROPHET_BASELINE`` is set.
    """
    if Prophet is None or not get_settings().enable_prophet_baseline:
        return {}
    models: dict[str, object] = {}
    for ward_id, ward_frame in train_frame.groupby("ward_id"):
        if len(ward_frame) < 10:
            continue
        prophet_frame = ward_frame[["timestamp", TARGET_COLUMN]].rename(
            columns={"timestamp": "ds", TARGET_COLUMN: "y"}
        )
        prophet_frame["ds"] = pd.to_datetime(prophet_frame["ds"], utc=True).dt.tz_convert(None)
        try:
            model = Prophet(daily_seasonality=True, weekly_seasonality=True, yearly_seasonality=False)
            model.fit(prophet_frame)
        except Exception:
            logger.warning("Prophet baseline failed for ward %s", ward_id, exc_info=True)
            continue
        models[str(ward_id)] = model
    return models


def train_forecast_model(master_table: pd.DataFrame) -> dict[str, object]:
    """Train the multi-horizon model and persist it to the artifact directory."""
    frame = build_training_frame(master_table)
    if frame.empty:
        raise ValueError("Not enough history to train a forecast model")
    train_frame, _ = time_based_split(frame)
    model, fitted_frame = _train_multi_horizon_model(train_frame)

    artifact: dict[str, object] = {
        "model": model,
        "prophet_models": _train_prophet_models(train_frame),
        "feature_columns": list(FEATURE_COLUMNS),
        "horizons": list(HORIZONS),
        # Metadata only: the fitted frame is not needed to serve a forecast and
        # keeping it would inflate the pickle with the whole training set.
        "trained_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "trained_rows": int(len(fitted_frame)),
        "trained_wards": sorted(str(value) for value in fitted_frame["ward_id"].unique()),
        "estimator": type(model.estimator).__name__ if hasattr(model, "estimator") else "unknown",
    }

    _ensure_artifacts_dir()
    with MODEL_PATH.open("wb") as handle:
        pickle.dump(artifact, handle)
    logger.info(
        "Forecast model trained: estimator=%s rows=%d wards=%d",
        artifact["estimator"], artifact["trained_rows"], len(artifact["trained_wards"]),
    )
    return artifact


def load_forecast_artifact(path: Path | None = None) -> dict[str, object]:
    model_path = path or MODEL_PATH
    with model_path.open("rb") as handle:
        return pickle.load(handle)


def persistence_forecast(series: pd.Series, horizons: Iterable[int] = HORIZONS) -> pd.DataFrame:
    last_value = float(series.iloc[-1])
    return pd.DataFrame({f"h{h}": [last_value] for h in horizons})


def _one_step_predictor(model):
    """Return the callable producing the 1-hour-ahead head of ``model``.

    ``MultiOutputRegressor`` fits one estimator per horizon, and calling its
    ``predict`` evaluates all of them. The recursive loop only needs the first
    head, so reaching for it directly makes a 72-step rollout roughly seven
    times cheaper without changing the output.
    """
    estimators = getattr(model, "estimators_", None)
    if estimators:
        return estimators[0].predict
    return lambda matrix: np.asarray(model.predict(matrix))[:, 0]


def recursive_forecast(
    artifact: dict[str, object],
    ward_frame: pd.DataFrame,
    steps: int | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Roll the 1-hour model forward ``steps`` times for a single ward.

    Returns ``(predictions, lower, upper)``. The interval widens with the
    square root of the horizon, reflecting accumulating one-step error.
    """
    steps = int(steps or DEFAULT_HORIZON_HOURS)
    if steps < 1:
        raise ValueError("steps must be at least 1")

    model = artifact["model"]
    feature_columns = list(artifact["feature_columns"])
    predict_one = _one_step_predictor(model)

    history = ward_frame.sort_values("timestamp").reset_index(drop=True)
    if history.empty:
        raise ValueError("Cannot forecast from an empty history frame")
    if TARGET_COLUMN not in history.columns:
        raise KeyError(f"History frame is missing the '{TARGET_COLUMN}' column")

    # Exogenous features are held at their last observed value; only the
    # AQI-derived lags and the calendar terms advance each step.
    template = history.iloc[-1:].reindex(columns=feature_columns).astype(float).fillna(0.0)
    column_index = {name: position for position, name in enumerate(feature_columns)}
    row = template.to_numpy(dtype=float)[0].copy()

    observed = [float(value) for value in history[TARGET_COLUMN].astype(float).tolist()]
    step_std = float(pd.Series(observed).diff().dropna().std() or 1.0)
    last_timestamp = pd.Timestamp(history["timestamp"].iloc[-1])

    predictions: list[float] = []
    lower: list[float] = []
    upper: list[float] = []

    for step in range(1, steps + 1):
        future_timestamp = last_timestamp + pd.Timedelta(hours=step)
        updates = {
            "aqi_lag_1h": observed[-1],
            "aqi_lag_24h": observed[-24] if len(observed) >= 24 else observed[-1],
            "aqi_rolling_6h": float(np.mean(observed[-6:])),
            "aqi_rolling_24h": float(np.mean(observed[-24:])),
            "hour_sin": np.sin(2 * np.pi * future_timestamp.hour / 24),
            "hour_cos": np.cos(2 * np.pi * future_timestamp.hour / 24),
            "dow_sin": np.sin(2 * np.pi * future_timestamp.day_of_week / 7),
            "dow_cos": np.cos(2 * np.pi * future_timestamp.day_of_week / 7),
        }
        for name, value in updates.items():
            position = column_index.get(name)
            if position is not None:
                row[position] = float(value)

        predicted = float(np.asarray(predict_one(row.reshape(1, -1))).ravel()[0])
        # AQI is a non-negative index; keep the rollout physically plausible.
        predicted = float(np.clip(predicted, 0.0, 1000.0))
        interval = 1.96 * step_std * np.sqrt(step)

        predictions.append(predicted)
        lower.append(max(predicted - interval, 0.0))
        upper.append(predicted + interval)
        observed.append(predicted)

    return np.asarray(predictions), np.asarray(lower), np.asarray(upper)


def evaluate_forecast(master_table: pd.DataFrame) -> dict[str, object]:
    """Train, then score each horizon against a persistence baseline.

    The baseline is "AQI stays where it is", which is the bar any short-horizon
    air-quality model has to clear to be worth deploying.
    """
    frame = build_training_frame(master_table)
    _, test_frame = time_based_split(frame)
    artifact = train_forecast_model(master_table)
    model = artifact["model"]

    test_frame = test_frame.dropna(subset=FEATURE_COLUMNS).reset_index(drop=True)
    if test_frame.empty:
        return {"comparison_table": pd.DataFrame(), "artifact_path": str(MODEL_PATH)}

    predictions = np.asarray(model.predict(_feature_matrix(test_frame)))
    rows: list[dict[str, object]] = []

    for index, horizon in enumerate(HORIZONS):
        actual = test_frame.groupby("ward_id", sort=False)[TARGET_COLUMN].shift(-horizon)
        # Persistence baseline: the value observed at prediction time.
        baseline = test_frame[TARGET_COLUMN].astype(float)
        mask = actual.notna().to_numpy()
        if not mask.any():
            continue

        y_true = actual.to_numpy(dtype=float)[mask]
        y_pred = predictions[mask, index]
        y_base = baseline.to_numpy(dtype=float)[mask]

        rows.append(
            {
                "horizon": f"aqi_t+{horizon}h",
                "samples": int(mask.sum()),
                "baseline_rmse": float(np.sqrt(mean_squared_error(y_true, y_base))),
                "baseline_mae": float(mean_absolute_error(y_true, y_base)),
                "model_rmse": float(np.sqrt(mean_squared_error(y_true, y_pred))),
                "model_mae": float(mean_absolute_error(y_true, y_pred)),
            }
        )

    comparison = pd.DataFrame(rows)
    if not comparison.empty:
        comparison["mae_improvement_pct"] = (
            (comparison["baseline_mae"] - comparison["model_mae"])
            / comparison["baseline_mae"].replace(0.0, np.nan)
            * 100.0
        ).round(2)
    return {"comparison_table": comparison, "artifact_path": str(MODEL_PATH)}
