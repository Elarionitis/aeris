"""Enforcement prioritisation agent.

Ranks wards for inspection by combining AQI severity, how long the ward has
been stuck in its band, the estimated share of controllable (industrial plus
construction) emissions, and corroborating registered sources within 1 km.
"""

from __future__ import annotations

import pandas as pd

from app.core.aqi import SEVERITY_WEIGHTS, aqi_band, severity_weight
from app.domain.wards import KNOWN_SOURCES, WARD_STATE, sources_for_ward
from app.ingestion._base import haversine_km

DISCLAIMER = (
    "Mock registry used for MVP prioritization; validate with live municipal data "
    "before operational use."
)

#: Radius within which a registered source corroborates a ward's AQI reading.
SOURCE_RADIUS_KM = 1.0
#: Each extra day in band adds this fraction to the score.
PERSISTENCE_WEIGHT = 0.12

__all__ = [
    "DISCLAIMER",
    "KNOWN_SOURCES",
    "SEVERITY_WEIGHTS",
    "SOURCE_RADIUS_KM",
    "WARD_STATE",
    "aqi_band",
    "build_priority_queue",
    "nearby_sources",
    "priority_queue_response",
]


def nearby_sources(ward_row: pd.Series, radius_km: float = SOURCE_RADIUS_KM) -> list[dict[str, object]]:
    """Registered sources within ``radius_km`` of the ward centroid."""
    matches: list[dict[str, object]] = []
    for _, source in sources_for_ward(str(ward_row.ward_id)).iterrows():
        distance = haversine_km(
            float(ward_row.latitude), float(ward_row.longitude),
            float(source.latitude), float(source.longitude),
        )
        if distance <= radius_km:
            matches.append(
                {
                    "source_name": str(source.source_name),
                    "source_type": str(source.source_type),
                    "latitude": float(source.latitude),
                    "longitude": float(source.longitude),
                    "distance_km": round(distance, 3),
                }
            )
    return sorted(matches, key=lambda item: item["distance_km"])


def _recommendation(ward_row: pd.Series, sources: list[dict[str, object]]) -> str:
    controllable = int(ward_row.industrial_pct + ward_row.construction_pct)
    return (
        f"Inspect {ward_row.ward_name}: {ward_row.dominant_source} contribution estimated at "
        f"{controllable}%, {len(sources)} registered sources within "
        f"{SOURCE_RADIUS_KM:g} km, AQI trending {aqi_band(float(ward_row.aqi))} for "
        f"{int(ward_row.aqi_trend_days)} consecutive days."
    )


def _score(ward_row: pd.Series, source_density: float) -> float:
    """Priority score; higher means inspect sooner.

    severity x controllable-emission share x source density, lifted by how long
    the ward has persisted in its current band.
    """
    persistence = 1.0 + PERSISTENCE_WEIGHT * max(int(ward_row.aqi_trend_days) - 1, 0)
    controllable = float(ward_row.industrial_pct + ward_row.construction_pct)
    return severity_weight(float(ward_row.aqi)) * controllable * source_density * persistence


def build_priority_queue(limit: int = 10) -> pd.DataFrame:
    """Rank every ward by inspection priority, highest first."""
    rows: list[dict[str, object]] = []
    for _, ward in WARD_STATE.iterrows():
        sources = nearby_sources(ward)
        # A ward with no registered source still carries its own severity.
        source_density = float(max(len(sources), 1))
        rows.append(
            {
                "ward_id": str(ward.ward_id),
                "ward_name": str(ward.ward_name),
                "aqi": int(ward.aqi),
                "aqi_band": aqi_band(float(ward.aqi)),
                "score": round(_score(ward, source_density), 3),
                "dominant_source": str(ward.dominant_source),
                "source_density_nearby": source_density,
                "source_coordinates": sources,
                "recommendation": _recommendation(ward, sources),
            }
        )
    frame = pd.DataFrame(rows).sort_values("score", ascending=False)
    return frame.head(max(int(limit), 1)).reset_index(drop=True)


def priority_queue_response(limit: int = 10) -> dict[str, object]:
    frame = build_priority_queue(limit)
    return {
        "items": frame.to_dict(orient="records"),
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "method": "severity_x_controllable_share_x_source_density_x_persistence",
        "disclaimer": DISCLAIMER,
    }
