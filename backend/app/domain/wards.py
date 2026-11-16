"""Ward registry, emission-source registry, and vulnerability profiles.

These tables stand in for municipal master data. They are deliberately kept in
one module so the API, the model layer, and the agent tools all resolve ward
identifiers identically.
"""

from __future__ import annotations

from difflib import get_close_matches

import pandas as pd

#: Current ward snapshot. ``aqi_trend_days`` counts consecutive days in band.
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

#: Registered emission sources used for geospatial corroboration.
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

#: Population-vulnerability profiles backing the citizen advisory agent.
WARD_VULNERABILITY = pd.DataFrame(
    [
        {"ward_id": "BTM", "ward_name": "BTM", "city": "Bengaluru", "aqi_forecast": 168, "school_poi_density": 4.8, "hospital_poi_density": 2.0, "elderly_pct": 8.5},
        {"ward_id": "HSR", "ward_name": "HSR Layout", "city": "Bengaluru", "aqi_forecast": 142, "school_poi_density": 5.6, "hospital_poi_density": 2.8, "elderly_pct": 7.9},
        {"ward_id": "Jayanagar", "ward_name": "Jayanagar", "city": "Bengaluru", "aqi_forecast": 88, "school_poi_density": 6.1, "hospital_poi_density": 4.2, "elderly_pct": 11.2},
        {"ward_id": "Mahadevapura", "ward_name": "Mahadevapura", "city": "Bengaluru", "aqi_forecast": 154, "school_poi_density": 3.9, "hospital_poi_density": 1.7, "elderly_pct": 7.4},
        {"ward_id": "Chennai Central", "ward_name": "Chennai Central", "city": "Chennai", "aqi_forecast": 119, "school_poi_density": 4.9, "hospital_poi_density": 3.6, "elderly_pct": 10.8},
    ]
)


def list_ward_ids() -> list[str]:
    return [str(value) for value in WARD_STATE["ward_id"].tolist()]


def resolve_ward_id(ward: str | None) -> str | None:
    """Resolve a user-supplied ward label to a canonical ``ward_id``.

    Accepts the id, the display name, or a close misspelling of either, so the
    LLM orchestrator does not have to echo identifiers byte-for-byte.
    """
    if ward is None:
        return None
    needle = str(ward).strip()
    if not needle:
        return None
    lowered = needle.casefold()

    for column in ("ward_id", "ward_name"):
        for _, row in WARD_STATE.iterrows():
            if str(row[column]).casefold() == lowered:
                return str(row.ward_id)

    candidates = {str(row.ward_id).casefold(): str(row.ward_id) for _, row in WARD_STATE.iterrows()}
    candidates.update({str(row.ward_name).casefold(): str(row.ward_id) for _, row in WARD_STATE.iterrows()})
    matches = get_close_matches(lowered, list(candidates), n=1, cutoff=0.78)
    return candidates[matches[0]] if matches else None


def ward_row(ward_id: str) -> pd.Series:
    """Return the ward snapshot row, raising ``KeyError`` when unknown."""
    match = WARD_STATE.loc[WARD_STATE["ward_id"].astype(str) == str(ward_id)]
    if match.empty:
        raise KeyError(str(ward_id))
    return match.iloc[0]


def ward_vulnerability_row(ward_id: str) -> pd.Series | None:
    match = WARD_VULNERABILITY.loc[WARD_VULNERABILITY["ward_id"].astype(str) == str(ward_id)]
    return None if match.empty else match.iloc[0]


def sources_for_ward(ward_id: str) -> pd.DataFrame:
    return KNOWN_SOURCES.loc[KNOWN_SOURCES["ward_id"].astype(str) == str(ward_id)]
