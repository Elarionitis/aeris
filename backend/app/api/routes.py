from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import pandas as pd

from app.models.advisory import generate_advisory_response
from app.models.enforcement import priority_queue_response
from app.models.attribution import load_attribution_model
from app.models.forecasting import load_forecast_artifact, recursive_forecast
from app.api.wards import router as wards_router

router = APIRouter(tags=["health"])
router.include_router(wards_router)


class ForecastRequest(BaseModel):
    history: list[dict]


@router.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/forecast/{ward_id}")
def forecast_ward(ward_id: str, payload: ForecastRequest) -> dict[str, object]:
    try:
        artifact = load_forecast_artifact()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail="Forecast model is not trained yet") from exc
    ward_frame = pd.DataFrame(payload.history)
    if ward_frame.empty or "ward_id" not in ward_frame.columns:
        raise HTTPException(status_code=404, detail="No history for ward_id")
    ward_frame = ward_frame.loc[ward_frame["ward_id"].astype(str) == str(ward_id)]
    if ward_frame.empty:
        raise HTTPException(status_code=404, detail="No history for ward_id")
    predictions, lower, upper = recursive_forecast(artifact, ward_frame)
    return {
        "ward_id": ward_id,
        "forecast": [
            {"horizon_hours": index + 1, "prediction": float(predictions[index]), "lower": float(lower[index]), "upper": float(upper[index])}
            for index in range(len(predictions))
        ],
    }


@router.get("/attribution/{ward_id}")
def attribution_ward(
    ward_id: str,
    traffic_density_index: float = 0.0,
    construction_permit_count: float = 0.0,
    industrial_stack_count: float = 0.0,
    thermal_anomaly_count_24h: float = 0.0,
) -> dict[str, object]:
    try:
        model = load_attribution_model()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail="Attribution model is not trained yet") from exc
    ward_frame = pd.DataFrame(
        [
            {
                "ward_id": ward_id,
                "traffic_density_index": traffic_density_index,
                "construction_permit_count": construction_permit_count,
                "industrial_stack_count": industrial_stack_count,
                "thermal_anomaly_count_24h": thermal_anomaly_count_24h,
                "aqi": 0.0,
            }
        ]
    )
    breakdown = model.predict_breakdown(ward_frame)
    return {
        "ward_id": ward_id,
        "timestamp": str(pd.Timestamp.utcnow()),
        "breakdown": breakdown,
        "confidence_score": round(model.confidence_score, 3),
        "method": model.method,
    }


@router.get("/enforcement/priority-queue")
def enforcement_priority_queue() -> dict[str, object]:
    return priority_queue_response(limit=10)


@router.get("/advisory/{ward_id}")
def advisory_ward(ward_id: str, lang: str = "en") -> dict[str, object]:
    try:
        return generate_advisory_response(ward_id, language=lang)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
