"""Analytical endpoints: forecast, attribution, enforcement, advisory."""

from __future__ import annotations

import pandas as pd
from fastapi import APIRouter, HTTPException, Path, Query

from app.api.orchestrator import router as orchestrator_router
from app.api.schemas import (
    AdvisoryResponse,
    AttributionResponse,
    ForecastRequest,
    ForecastResponse,
    HealthResponse,
    PriorityQueueResponse,
)
from app.api.wards import router as wards_router
from app.core.aqi import band_scale
from app.core.config import get_settings
from app.core.logging import get_logger
from app.domain.wards import ward_row
from app.models.advisory import (
    LANGUAGE_NAMES,
    generate_advisory_response,
    normalise_language,
)
from app.models.attribution import FEATURES as ATTRIBUTION_FEATURES, load_attribution_model
from app.models.bootstrap import model_status, ward_history
from app.models.enforcement import priority_queue_response
from app.models.forecasting import load_forecast_artifact, recursive_forecast

logger = get_logger(__name__)

router = APIRouter()
router.include_router(wards_router)
router.include_router(orchestrator_router)

WardIdPath = Path(..., min_length=1, max_length=64, description="Ward identifier.")


def _require_ward(ward_id: str) -> pd.Series:
    try:
        return ward_row(ward_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown ward_id: {ward_id}") from exc


def _require_forecast_artifact() -> dict[str, object]:
    try:
        return load_forecast_artifact()
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=503,
            detail="Forecast model is not trained yet; restart with AUTO_TRAIN_ON_STARTUP enabled.",
        ) from exc


@router.get("/health", response_model=HealthResponse, tags=["health"])
def health_check() -> dict[str, object]:
    """Readiness probe covering the model artifacts and the orchestrator."""
    from app.agents.llm import llm_info

    settings = get_settings()
    models = model_status()
    return {
        "status": "ok" if models.ready else "degraded",
        "version": settings.app_version,
        "environment": settings.environment,
        "models": models.as_dict(),
        "orchestrator": llm_info(settings).as_dict(),
    }


@router.get("/meta", tags=["health"])
def service_meta() -> dict[str, object]:
    """Static reference data the dashboard needs to render consistently."""
    settings = get_settings()
    return {
        "app_name": settings.app_name,
        "version": settings.app_version,
        "city": "Bengaluru",
        "band_scale": band_scale(),
        "languages": [{"code": code, "name": name} for code, name in LANGUAGE_NAMES.items()],
        "max_forecast_hours": settings.forecast_horizon_hours,
    }


@router.post("/forecast/{ward_id}", response_model=ForecastResponse, tags=["forecast"])
def forecast_ward(payload: ForecastRequest, ward_id: str = WardIdPath) -> dict[str, object]:
    """Forecast from caller-supplied feature history."""
    _require_ward(ward_id)
    artifact = _require_forecast_artifact()

    frame = pd.DataFrame(payload.history)
    if frame.empty or "ward_id" not in frame.columns:
        raise HTTPException(status_code=422, detail="history must contain rows with a ward_id column")
    frame = frame.loc[frame["ward_id"].astype(str) == str(ward_id)]
    if frame.empty:
        raise HTTPException(status_code=404, detail=f"No history rows for ward_id: {ward_id}")
    if "timestamp" not in frame.columns or "aqi" not in frame.columns:
        raise HTTPException(status_code=422, detail="history rows require 'timestamp' and 'aqi'")

    frame = frame.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce")
    if frame["timestamp"].isna().all():
        raise HTTPException(status_code=422, detail="history timestamps could not be parsed")

    steps = payload.steps or get_settings().forecast_horizon_hours
    try:
        predictions, lower, upper = recursive_forecast(artifact, frame, steps=steps)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return _forecast_payload(ward_id, predictions, lower, upper, "request_history")


@router.get("/forecast/{ward_id}", response_model=ForecastResponse, tags=["forecast"])
def forecast_ward_from_baseline(
    ward_id: str = WardIdPath,
    hours: int = Query(default=72, ge=1, le=168, description="Horizon in hours."),
) -> dict[str, object]:
    """Forecast from the service's own ward history.

    The dashboard uses this so it does not have to hold a feature history
    client-side. It runs the same trained model as the POST endpoint; only the
    source of the seed history differs.
    """
    _require_ward(ward_id)
    artifact = _require_forecast_artifact()
    steps = min(hours, get_settings().forecast_horizon_hours)
    history = ward_history(ward_id, hours=48)
    predictions, lower, upper = recursive_forecast(artifact, history, steps=steps)
    return _forecast_payload(ward_id, predictions, lower, upper, "baseline_history")


def _forecast_payload(ward_id: str, predictions, lower, upper, source: str) -> dict[str, object]:
    return {
        "ward_id": str(ward_id),
        "source": source,
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "forecast": [
            {
                "horizon_hours": index + 1,
                "prediction": round(float(predictions[index]), 2),
                "lower": round(float(lower[index]), 2),
                "upper": round(float(upper[index]), 2),
            }
            for index in range(len(predictions))
        ],
    }


@router.get("/attribution/{ward_id}", response_model=AttributionResponse, tags=["attribution"])
def attribution_ward(
    ward_id: str = WardIdPath,
    traffic_density_index: float | None = Query(default=None, ge=0.0),
    construction_permit_count: float | None = Query(default=None, ge=0.0),
    industrial_stack_count: float | None = Query(default=None, ge=0.0),
    thermal_anomaly_count_24h: float = Query(default=0.0, ge=0.0),
) -> dict[str, object]:
    """Source breakdown for a ward, with optional feature overrides.

    Omitted features default to the ward's most recent observed values, so a
    caller can probe one lever (say, halving traffic) in isolation.
    """
    _require_ward(ward_id)
    try:
        model = load_attribution_model()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail="Attribution model is not trained yet") from exc

    latest = ward_history(ward_id, hours=48).iloc[-1:].reindex(columns=ATTRIBUTION_FEATURES).copy()
    overrides = {
        "traffic_density_index": traffic_density_index,
        "construction_permit_count": construction_permit_count,
        "industrial_stack_count": industrial_stack_count,
        "thermal_anomaly_count_24h": thermal_anomaly_count_24h,
    }
    for column, value in overrides.items():
        if value is not None:
            latest[column] = float(value)

    return {
        "ward_id": str(ward_id),
        "timestamp": pd.Timestamp.now(tz="UTC").isoformat(),
        "breakdown": model.predict_breakdown(latest),
        "confidence_score": round(float(model.confidence_score), 3),
        "method": model.method,
    }


@router.get("/enforcement/priority-queue", response_model=PriorityQueueResponse, tags=["enforcement"])
def enforcement_priority_queue(
    limit: int = Query(default=10, ge=1, le=50, description="How many wards to return."),
) -> dict[str, object]:
    """Wards ranked by inspection priority, highest score first."""
    return priority_queue_response(limit=limit)


@router.get("/advisory/{ward_id}", response_model=AdvisoryResponse, tags=["advisory"])
def advisory_ward(
    ward_id: str = WardIdPath,
    lang: str = Query(default="en", description=f"One of: {', '.join(LANGUAGE_NAMES)}."),
) -> dict[str, object]:
    """Multilingual citizen health advisory for a ward."""
    try:
        return generate_advisory_response(ward_id, language=normalise_language(lang))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
