from __future__ import annotations

from dataclasses import dataclass
from math import radians, sin, cos, asin, sqrt
from pathlib import Path
from typing import Iterable

import pandas as pd


ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"
DISCLAIMER = "Mock registry used for MVP prioritization; validate with live municipal data before operational use."

SEVERITY_WEIGHTS = {"Good": 0.2, "Moderate": 0.6, "Poor": 1.0, "Very Poor": 1.4, "Severe": 1.8}

WARD_STATE = pd.DataFrame(
    [
        {"ward_id": "BTM", "ward_name": "BTM", "latitude": 12.9166, "longitude": 77.6101, "aqi": 168, "aqi_trend_days": 4, "industrial_pct": 31, "construction_pct": 18, "dominant_source": "industrial"},
        {"ward_id": "HSR", "ward_name": "HSR Layout", "latitude": 12.9116, "longitude": 77.6389, "aqi": 142, "aqi_trend_days": 3, "industrial_pct": 24, "construction_pct": 21, "dominant_source": "construction"},
        {"ward_id": "Yelahanka", "ward_name": "Yelahanka", "latitude": 13.1000, "longitude": 77.5963, "aqi": 118, "aqi_trend_days": 2, "industrial_pct": 19, "construction_pct": 11, "dominant_source": "industrial"},
        {"ward_id": "Koramangala", "ward_name": "Koramangala", "latitude": 12.9352, "longitude": 77.6245, "aqi": 96, "aqi_trend_days": 2, "industrial_pct": 11, "construction_pct": 12, "dominant_source": "construction"},
        {"ward_id": "Jayanagar", "ward_name": "Jayanagar", "latitude": 12.9250, "longitude": 77.5938, "aqi": 89, "aqi_trend_days": 1, "industrial_pct": 7, "construction_pct": 6, "dominant_source": "traffic"},
        {"ward_id": "Mahadevapura", "ward_name": "Mahadevapura", "latitude": 12.9915, "longitude": 77.6957, "aqi": 154, "aqi_trend_days": 5, "industrial_pct": 28, "construction_pct": 19, "dominant_source": "industrial"},
        {"ward_id": "RR Nagar", "ward_name": "RR Nagar", "latitude": 12.9279, "longitude": 77.5190, "aqi": 101, "aqi_trend_days": 2, "industrial_pct": 13, "construction_pct": 15, "dominant_source": "construction"},
        {"ward_id": "Electronic City", "ward_name": "Electronic City", "latitude": 12.8456, "longitude": 77.6600, "aqi": 132, "aqi_trend_days": 3, "industrial_pct": 25, "construction_pct": 14, "dominant_source": "industrial"},
    ]
)

KNOWN_SOURCES = pd.DataFrame(
    [
        {"ward_id": "BTM", "source_type": "industrial", "source_name": "Stack cluster A", "latitude": 12.9210, "longitude": 77.6160},
        {"ward_id": "BTM", "source_type": "construction", "source_name": "Metro corridor site", "latitude": 12.9148, "longitude": 77.6080},
        {"ward_id": "BTM", "source_type": "waste_burning", "source_name": "Roadside hotspot", "latitude": 12.9192, "longitude": 77.6032},
        {"ward_id": "HSR", "source_type": "industrial", "source_name": "Small-scale workshop belt", "latitude": 12.9102, "longitude": 77.6428},
        {"ward_id": "HSR", "source_type": "construction", "source_name": "Apartment redevelopment", "latitude": 12.9182, "longitude": 77.6369},
        {"ward_id": "Yelahanka", "source_type": "industrial", "source_name": "Peripheral industrial stack", "latitude": 13.1048, "longitude": 77.5905},
        {"ward_id": "Mahadevapura", "source_type": "industrial", "source_name": "Tech park utilities stack", "latitude": 12.9958, "longitude": 77.7013},
        {"ward_id": "Mahadevapura", "source_type": "construction", "source_name": "Flyover work zone", "latitude": 12.9865, "longitude": 77.6895},
        {"ward_id": "Electronic City", "source_type": "industrial", "source_name": "Manufacturing cluster", "latitude": 12.8480, "longitude": 77.6629},
        {"ward_id": "Electronic City", "source_type": "waste_burning", "source_name": "Vacant-lot burn spot", "latitude": 12.8418, "longitude": 77.6556},
    ]
)


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    earth_radius_km = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * earth_radius_km * asin(sqrt(a))


def aqi_band(aqi: float) -> str:
    if aqi <= 50:
        return "Good"
    if aqi <= 100:
        return "Moderate"
    if aqi <= 200:
        return "Poor"
    if aqi <= 300:
        return "Very Poor"
    return "Severe"


def _source_density_nearby(ward_row: pd.Series, source_frame: pd.DataFrame, radius_km: float = 1.0) -> tuple[float, list[dict[str, object]]]:
    matches = []
    for _, source in source_frame.iterrows():
        distance = _haversine_km(ward_row.latitude, ward_row.longitude, source.latitude, source.longitude)
        if distance <= radius_km:
            matches.append({"source_name": source.source_name, "source_type": source.source_type, "latitude": float(source.latitude), "longitude": float(source.longitude), "distance_km": round(distance, 3)})
    density = max(len(matches), 1)
    return float(density), matches


def _recommendation(ward_row: pd.Series, sources: list[dict[str, object]]) -> str:
    dominant = ward_row.dominant_source
    nearby_count = len(sources)
    return (
        f"Inspect {ward_row.ward_name}: {dominant} contribution estimated at {int(ward_row.industrial_pct + ward_row.construction_pct)}%, "
        f"{nearby_count} registered sources within 1 km, AQI trending {aqi_band(float(ward_row.aqi))} for {int(ward_row.aqi_trend_days)} consecutive days."
    )


def build_priority_queue(limit: int = 10) -> pd.DataFrame:
    rows = []
    for _, ward in WARD_STATE.iterrows():
        source_density, source_matches = _source_density_nearby(ward, KNOWN_SOURCES[KNOWN_SOURCES["ward_id"] == ward.ward_id])
        severity_weight = SEVERITY_WEIGHTS[aqi_band(float(ward.aqi))]
        score = severity_weight * float(ward.industrial_pct + ward.construction_pct) * source_density
        rows.append(
            {
                "ward_id": ward.ward_id,
                "ward_name": ward.ward_name,
                "aqi": int(ward.aqi),
                "aqi_band": aqi_band(float(ward.aqi)),
                "score": round(score, 3),
                "dominant_source": ward.dominant_source,
                "source_density_nearby": source_density,
                "source_coordinates": source_matches,
                "recommendation": _recommendation(ward, source_matches),
            }
        )
    frame = pd.DataFrame(rows).sort_values("score", ascending=False).head(limit).reset_index(drop=True)
    return frame


def priority_queue_response(limit: int = 10) -> dict[str, object]:
    frame = build_priority_queue(limit)
    return {"items": frame.to_dict(orient="records"), "disclaimer": DISCLAIMER}
