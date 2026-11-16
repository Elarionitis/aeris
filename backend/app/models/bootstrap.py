"""Model bootstrapping and ward history synthesis.

Trained artifacts are not committed to the repository, so a fresh checkout has
no ``forecast_model.pkl`` or ``attribution_model.pkl`` and every model-backed
endpoint fails with a 503. This module generates a reproducible ward-hour
master table from the ward registry and trains both models from it on startup,
so the service is useful immediately and is replaced feed-by-feed as live
ingestion comes online.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from app.core.logging import get_logger
from app.domain.wards import WARD_STATE, ward_row
from app.models import attribution as attribution_module
from app.models import forecasting as forecasting_module
from app.models.attribution import (
    FEATURES as ATTRIBUTION_FEATURES,
    fit_attribution_model,
    load_attribution_model,
)
from app.models.forecasting import load_forecast_artifact, train_forecast_model

logger = get_logger(__name__)

#: Hours of synthesised history per ward. Two weeks covers the 24h lags, the
#: weekly seasonality term, and leaves a usable hold-out split.
HISTORY_HOURS = 14 * 24
RANDOM_SEED = 20260101

# Reentrant: ensure_models holds the lock while calling _master_table.
_LOCK = threading.RLock()
_CACHE: dict[str, Any] = {}

__all__ = [
    "BootstrapStatus",
    "HISTORY_HOURS",
    "ensure_models",
    "model_status",
    "synthetic_master_table",
    "ward_history",
]


@dataclass
class BootstrapStatus:
    """Outcome of a model readiness check."""

    forecast_ready: bool = False
    attribution_ready: bool = False
    forecast_trained: bool = False
    attribution_trained: bool = False
    errors: list[str] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return self.forecast_ready and self.attribution_ready

    def as_dict(self) -> dict[str, object]:
        return {
            "forecast_model": "ready" if self.forecast_ready else "unavailable",
            "attribution_model": "ready" if self.attribution_ready else "unavailable",
            "trained_this_startup": sorted(
                name
                for name, trained in (
                    ("forecast", self.forecast_trained),
                    ("attribution", self.attribution_trained),
                )
                if trained
            ),
            "errors": list(self.errors),
        }


def _diurnal(hour: np.ndarray) -> np.ndarray:
    """Two daily AQI peaks: morning and evening traffic."""
    return 14.0 * np.sin(2 * np.pi * (hour - 7) / 24) + 7.0 * np.sin(4 * np.pi * (hour - 4) / 24)


def synthetic_master_table(hours: int = HISTORY_HOURS, seed: int = RANDOM_SEED) -> pd.DataFrame:
    """Build a deterministic ward-hour master table.

    Each ward oscillates around its registry AQI with a diurnal and weekly
    cycle, mean-reverting noise, and source-activity features correlated with
    its land-use mix. The same seed always yields the same table, so training
    is reproducible and tests are stable.
    """
    hours = max(int(hours), 48)
    rng = np.random.default_rng(seed)
    end = pd.Timestamp.now(tz="UTC").floor("h")
    timestamps = pd.date_range(end=end, periods=hours, freq="h", tz="UTC")

    hour_of_day = timestamps.hour.to_numpy(dtype=float)
    day_of_week = timestamps.dayofweek.to_numpy(dtype=float)
    weekday_factor = np.where(day_of_week >= 5, 0.82, 1.0)

    frames: list[pd.DataFrame] = []
    for _, ward in WARD_STATE.iterrows():
        base = float(ward.aqi)
        industrial = float(ward.industrial_pct)
        construction = float(ward.construction_pct)

        # Mean-reverting (AR(1)) residual keeps the series autocorrelated, which
        # is what makes lag features informative rather than noise.
        shocks = rng.normal(0.0, 6.0, size=hours)
        residual = np.zeros(hours)
        for index in range(1, hours):
            residual[index] = 0.82 * residual[index - 1] + shocks[index]

        wind_speed = np.clip(2.6 + 1.5 * np.sin(2 * np.pi * hour_of_day / 24) + rng.normal(0, 0.5, hours), 0.2, 12.0)
        wind_direction = (180 + 70 * np.sin(2 * np.pi * np.arange(hours) / 53) + rng.normal(0, 18, hours)) % 360
        temperature = 24.0 + 6.0 * np.sin(2 * np.pi * (hour_of_day - 9) / 24) + rng.normal(0, 1.1, hours)
        humidity = np.clip(62.0 - 0.8 * (temperature - 24.0) + rng.normal(0, 4.0, hours), 15.0, 99.0)

        traffic = np.clip(
            (6.0 + 0.08 * (100 - industrial - construction)) * weekday_factor
            * (1.0 + 0.45 * np.sin(2 * np.pi * (hour_of_day - 8) / 24))
            + rng.normal(0, 0.4, hours),
            0.1, 30.0,
        )
        construction_permits = np.clip(construction / 10.0 + rng.normal(0, 0.18, hours), 0.0, None)
        industrial_stacks = np.clip(industrial / 10.0 + rng.normal(0, 0.14, hours), 0.0, None)
        thermal_anomalies = rng.poisson(0.18 + industrial / 260.0, hours).astype(float)

        # Stronger wind disperses pollution; this is the main weather coupling.
        ventilation = -2.4 * (wind_speed - wind_speed.mean())
        aqi = (
            base
            + _diurnal(hour_of_day) * weekday_factor
            + residual
            + ventilation
            + 2.1 * thermal_anomalies
            + 0.045 * humidity
        )
        aqi = np.clip(aqi, 15.0, 480.0)

        frames.append(
            pd.DataFrame(
                {
                    "ward_id": str(ward.ward_id),
                    "ward_name": str(ward.ward_name),
                    "timestamp": timestamps,
                    "aqi": np.round(aqi, 2),
                    "wind_speed": np.round(wind_speed, 3),
                    "wind_direction": np.round(wind_direction, 2),
                    "temperature": np.round(temperature, 2),
                    "humidity": np.round(humidity, 2),
                    "traffic_density_index": np.round(traffic, 3),
                    "construction_permit_count": np.round(construction_permits, 3),
                    "industrial_stack_count": np.round(industrial_stacks, 3),
                    "thermal_anomaly_count_24h": thermal_anomalies,
                }
            )
        )

    table = pd.concat(frames, ignore_index=True)
    return table.sort_values(["ward_id", "timestamp"]).reset_index(drop=True)


def _master_table() -> pd.DataFrame:
    """Process-cached master table; cheap enough to build once, never twice."""
    with _LOCK:
        table = _CACHE.get("master_table")
        if table is None:
            table = synthetic_master_table()
            _CACHE["master_table"] = table
            logger.info(
                "Synthesised baseline master table: %d rows across %d wards",
                len(table), table["ward_id"].nunique(),
            )
        return table


def ward_history(ward_id: str, hours: int = 48) -> pd.DataFrame:
    """Most recent ``hours`` of history for a ward, for seeding a forecast.

    Raises ``KeyError`` when the ward is not in the registry.
    """
    ward_row(ward_id)  # validates the identifier
    table = _master_table()
    frame = table.loc[table["ward_id"].astype(str) == str(ward_id)]
    return frame.tail(max(int(hours), 25)).copy().reset_index(drop=True)


def model_status() -> BootstrapStatus:
    """Report which artifacts can currently be loaded, without training."""
    status = BootstrapStatus()
    try:
        load_forecast_artifact()
        status.forecast_ready = True
    except Exception:
        status.forecast_ready = False
    try:
        load_attribution_model()
        status.attribution_ready = True
    except Exception:
        status.attribution_ready = False
    return status


def ensure_models(force: bool = False) -> BootstrapStatus:
    """Train any missing model artifact from the baseline master table.

    Never raises: a training failure is logged and reported through the
    returned status so the rest of the API still starts.
    """
    with _LOCK:
        status = BootstrapStatus()
        table: pd.DataFrame | None = None

        if force or not forecasting_module.MODEL_PATH.exists():
            try:
                table = _master_table()
                train_forecast_model(table)
                status.forecast_trained = True
                logger.info("Forecast model trained from baseline master table")
            except Exception as exc:
                status.errors.append(f"forecast training failed: {exc}")
                logger.exception("Forecast model training failed")

        if force or not attribution_module.ATTRIBUTION_PATH.exists():
            try:
                table = table if table is not None else _master_table()
                columns = ["ward_id", "timestamp", "aqi", *ATTRIBUTION_FEATURES]
                fit_attribution_model(table[columns])
                status.attribution_trained = True
                logger.info("Attribution model trained from baseline master table")
            except Exception as exc:
                status.errors.append(f"attribution training failed: {exc}")
                logger.exception("Attribution model training failed")

    probe = model_status()
    status.forecast_ready = probe.forecast_ready
    status.attribution_ready = probe.attribution_ready
    return status
