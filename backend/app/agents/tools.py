"""The three analytical agents, exposed as LLM-callable tools.

Each tool is a thin, strongly-typed wrapper over one model agent:

* ``forecast_ward_aqi``        -> forecasting agent (multi-horizon rollout)
* ``attribute_ward_sources``   -> attribution agent (NNLS source split)
* ``rank_enforcement_priority`` -> enforcement agent (inspection ranking)

``list_wards`` is a grounding helper rather than an agent: it lets the model
discover valid ward identifiers instead of inventing them.

Tools call the model layer in-process, never over HTTP, so the orchestrator
adds no network hop. Every tool returns JSON-serialisable data and reports
failures as ``{"error": ...}`` rather than raising, because an exception inside
a tool call would abort the whole graph run.
"""

from __future__ import annotations

from typing import Annotated, Any, Callable

from langchain_core.tools import StructuredTool

from app.core.aqi import aqi_band, band_scale
from app.core.config import get_settings
from app.core.logging import get_logger
from app.domain.wards import WARD_STATE, list_ward_ids, resolve_ward_id, ward_row
from app.models.attribution import FEATURES as ATTRIBUTION_FEATURES, load_attribution_model
from app.models.bootstrap import ward_history
from app.models.enforcement import DISCLAIMER as ENFORCEMENT_DISCLAIMER, priority_queue_response
from app.models.forecasting import load_forecast_artifact, recursive_forecast

logger = get_logger(__name__)

#: Horizons summarised for the model so it never has to read 72 raw points.
SUMMARY_HORIZONS = (1, 6, 12, 24, 48, 72)


def _unknown_ward(ward: str) -> dict[str, Any]:
    return {
        "error": f"Unknown ward '{ward}'.",
        "known_wards": list_ward_ids(),
        "hint": "Call list_wards to see valid ward identifiers.",
    }


def list_wards() -> dict[str, Any]:
    """List every monitored ward with its current AQI and CPCB band.

    Call this first when the user names a place you are unsure about, or when
    they ask a city-wide question and you need the full ward roster.
    """
    wards = [
        {
            "ward_id": str(row.ward_id),
            "ward_name": str(row.ward_name),
            "aqi": int(row.aqi),
            "band": aqi_band(float(row.aqi)),
            "days_in_band": int(row.aqi_trend_days),
            "dominant_source": str(row.dominant_source),
        }
        for _, row in WARD_STATE.iterrows()
    ]
    wards.sort(key=lambda item: item["aqi"], reverse=True)
    city_average = round(sum(item["aqi"] for item in wards) / max(len(wards), 1), 1)
    return {
        "city": "Bengaluru",
        "ward_count": len(wards),
        "city_average_aqi": city_average,
        "city_average_band": aqi_band(city_average),
        "wards": wards,
        "band_scale": band_scale(),
    }


def forecast_ward_aqi(
    ward: Annotated[str, "Ward identifier or display name, e.g. 'BTM' or 'HSR Layout'."],
    hours: Annotated[int, "Forecast horizon in hours, 1 to 72."] = 24,
) -> dict[str, Any]:
    """Forecast a ward's AQI up to 72 hours ahead with confidence bounds.

    Use this for any question about what the air will be like later today,
    tonight, tomorrow, or over the next few days. Returns the peak and its
    timing, a per-horizon summary, and the band the ward is heading into.
    """
    settings = get_settings()
    ward_id = resolve_ward_id(ward)
    if ward_id is None:
        return _unknown_ward(ward)

    horizon = max(1, min(int(hours or 24), settings.forecast_horizon_hours))
    try:
        artifact = load_forecast_artifact()
    except FileNotFoundError:
        return {"error": "Forecast model is not trained yet.", "ward_id": ward_id}

    try:
        history = ward_history(ward_id, hours=48)
        predictions, lower, upper = recursive_forecast(artifact, history, steps=horizon)
    except Exception as exc:
        logger.exception("Forecast tool failed for ward %s", ward_id)
        return {"error": f"Forecast failed: {exc}", "ward_id": ward_id}

    current_aqi = float(history["aqi"].iloc[-1])
    peak_index = int(predictions.argmax())
    summary = [
        {
            "horizon_hours": step,
            "aqi": round(float(predictions[step - 1]), 1),
            "band": aqi_band(float(predictions[step - 1])),
            "lower": round(float(lower[step - 1]), 1),
            "upper": round(float(upper[step - 1]), 1),
        }
        for step in SUMMARY_HORIZONS
        if step <= horizon
    ]
    mean_forecast = float(predictions.mean())
    return {
        "agent": "forecasting",
        "ward_id": ward_id,
        "ward_name": str(ward_row(ward_id).ward_name),
        "horizon_hours": horizon,
        "current_aqi": round(current_aqi, 1),
        "current_band": aqi_band(current_aqi),
        "mean_forecast_aqi": round(mean_forecast, 1),
        "peak": {
            "aqi": round(float(predictions[peak_index]), 1),
            "band": aqi_band(float(predictions[peak_index])),
            "in_hours": peak_index + 1,
        },
        "direction": "worsening" if mean_forecast > current_aqi + 2 else "improving" if mean_forecast < current_aqi - 2 else "stable",
        "by_horizon": summary,
        "method": "recursive multi-horizon gradient boosting on lagged AQI, weather, and source features",
    }


def attribute_ward_sources(
    ward: Annotated[str, "Ward identifier or display name."],
    thermal_anomaly_count_24h: Annotated[float, "Satellite fire/thermal detections in the last 24h."] = 0.0,
) -> dict[str, Any]:
    """Break a ward's pollution into traffic, construction, industrial, and other shares.

    Use this for "why" questions: what is causing the pollution here, which
    source dominates, what should be targeted. Shares sum to 100 and carry an
    R-squared confidence score.
    """
    ward_id = resolve_ward_id(ward)
    if ward_id is None:
        return _unknown_ward(ward)

    try:
        model = load_attribution_model()
    except FileNotFoundError:
        return {"error": "Attribution model is not trained yet.", "ward_id": ward_id}

    try:
        history = ward_history(ward_id, hours=48)
        latest = history.iloc[-1:].copy()
        latest["thermal_anomaly_count_24h"] = float(thermal_anomaly_count_24h or 0.0)
        breakdown = model.predict_breakdown(latest[ATTRIBUTION_FEATURES])
    except Exception as exc:
        logger.exception("Attribution tool failed for ward %s", ward_id)
        return {"error": f"Attribution failed: {exc}", "ward_id": ward_id}

    row = ward_row(ward_id)
    dominant = max(breakdown.items(), key=lambda item: item[1])
    return {
        "agent": "attribution",
        "ward_id": ward_id,
        "ward_name": str(row.ward_name),
        "current_aqi": int(row.aqi),
        "current_band": aqi_band(float(row.aqi)),
        "breakdown_pct": breakdown,
        "dominant_source": dominant[0],
        "dominant_source_pct": dominant[1],
        "registry_dominant_source": str(row.dominant_source),
        "confidence_score": round(float(model.confidence_score), 3),
        "method": model.method,
        "caveat": "Shares are modelled from source-activity proxies, not stack-level measurement.",
    }


def rank_enforcement_priority(
    limit: Annotated[int, "How many wards to return, 1 to 10."] = 5,
) -> dict[str, Any]:
    """Rank wards by inspection priority for enforcement teams.

    Use this for "where should we act first" questions. The score combines AQI
    severity, how long the ward has stayed in its band, the controllable
    emission share, and registered sources within 1 km.
    """
    try:
        payload = priority_queue_response(limit=max(1, min(int(limit or 5), 10)))
    except Exception as exc:
        logger.exception("Enforcement tool failed")
        return {"error": f"Enforcement ranking failed: {exc}"}

    items = [
        {
            "rank": index + 1,
            "ward_id": item["ward_id"],
            "ward_name": item["ward_name"],
            "aqi": item["aqi"],
            "band": item["aqi_band"],
            "score": item["score"],
            "dominant_source": item["dominant_source"],
            "sources_within_1km": int(item["source_density_nearby"]),
            "recommendation": item["recommendation"],
        }
        for index, item in enumerate(payload["items"])
    ]
    return {
        "agent": "enforcement",
        "items": items,
        "method": payload["method"],
        "disclaimer": ENFORCEMENT_DISCLAIMER,
    }


#: Public callables, keyed by the name the LLM sees.
AGENT_FUNCTIONS: dict[str, Callable[..., dict[str, Any]]] = {
    "list_wards": list_wards,
    "forecast_ward_aqi": forecast_ward_aqi,
    "attribute_ward_sources": attribute_ward_sources,
    "rank_enforcement_priority": rank_enforcement_priority,
}

#: Which underlying agent each tool fronts; surfaced in the API trace.
TOOL_AGENTS: dict[str, str] = {
    "list_wards": "registry",
    "forecast_ward_aqi": "forecasting",
    "attribute_ward_sources": "attribution",
    "rank_enforcement_priority": "enforcement",
}


def build_tools() -> list[StructuredTool]:
    """Wrap the agent functions as LangChain structured tools."""
    return [
        StructuredTool.from_function(func=function, name=name, parse_docstring=False)
        for name, function in AGENT_FUNCTIONS.items()
    ]


def tool_catalogue() -> list[dict[str, object]]:
    """Describe the tools for the ``/orchestrator/tools`` endpoint."""
    return [
        {
            "name": tool.name,
            "agent": TOOL_AGENTS.get(tool.name, "unknown"),
            "description": (tool.description or "").strip().splitlines()[0],
            "parameters": tool.args_schema.model_json_schema() if tool.args_schema else {},
        }
        for tool in build_tools()
    ]
