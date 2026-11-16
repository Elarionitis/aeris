"""Single source of truth for AQI banding.

The backend and the dashboard previously disagreed about band names (an AQI of
168 was reported as "Poor" by the API and "Moderate" by the UI). Both now use
the CPCB National Air Quality Index scale defined here.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AqiBand:
    label: str
    lower: int
    upper: int
    color: str
    severity_weight: float


#: CPCB National AQI breakpoints, ordered from cleanest to most hazardous.
AQI_BANDS: tuple[AqiBand, ...] = (
    AqiBand("Good", 0, 50, "#009865", 0.2),
    AqiBand("Satisfactory", 51, 100, "#A3C853", 0.4),
    AqiBand("Moderate", 101, 200, "#FFD500", 0.7),
    AqiBand("Poor", 201, 300, "#FF7E00", 1.1),
    AqiBand("Very Poor", 301, 400, "#FF0000", 1.5),
    AqiBand("Severe", 401, 10_000, "#7E0023", 1.9),
)

BAND_LABELS: tuple[str, ...] = tuple(band.label for band in AQI_BANDS)
SEVERITY_WEIGHTS: dict[str, float] = {band.label: band.severity_weight for band in AQI_BANDS}
BAND_COLORS: dict[str, str] = {band.label: band.color for band in AQI_BANDS}

#: Bands at or above which outdoor exposure guidance becomes restrictive.
SENSITIVE_GROUP_BANDS: frozenset[str] = frozenset({"Moderate", "Poor", "Very Poor", "Severe"})
UNHEALTHY_BANDS: frozenset[str] = frozenset({"Poor", "Very Poor", "Severe"})


def band_for(aqi: float) -> AqiBand:
    """Return the CPCB band containing ``aqi`` (clamped at both ends)."""
    value = max(float(aqi), 0.0)
    for band in AQI_BANDS:
        if value <= band.upper:
            return band
    return AQI_BANDS[-1]


def aqi_band(aqi: float) -> str:
    """Return the CPCB band label for ``aqi``."""
    return band_for(aqi).label


def severity_weight(aqi: float) -> float:
    """Return the enforcement severity multiplier for ``aqi``."""
    return band_for(aqi).severity_weight


def band_color(aqi: float) -> str:
    return band_for(aqi).color


def is_unhealthy(aqi: float) -> bool:
    return aqi_band(aqi) in UNHEALTHY_BANDS


def band_scale() -> list[dict[str, object]]:
    """Serialisable band table, exposed to the dashboard via ``/meta``."""
    return [
        {
            "label": band.label,
            "lower": band.lower,
            "upper": None if band.upper >= 10_000 else band.upper,
            "color": band.color,
            "severity_weight": band.severity_weight,
        }
        for band in AQI_BANDS
    ]
