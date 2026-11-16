"""Ward registry endpoint, including map geometry."""

from __future__ import annotations

from math import cos, radians

from fastapi import APIRouter

from app.api.schemas import WardResponse
from app.core.aqi import aqi_band, band_color
from app.domain.wards import WARD_STATE

router = APIRouter(tags=["wards"])

#: Half-width of the stand-in ward polygon. Real BBMP boundaries replace this.
WARD_HALF_WIDTH_KM = 0.9
KM_PER_DEGREE_LATITUDE = 110.574
KM_PER_DEGREE_LONGITUDE_AT_EQUATOR = 111.320


def _square_geometry(lat: float, lon: float, offset_km: float = WARD_HALF_WIDTH_KM) -> dict[str, object]:
    """A square polygon centred on the ward, as a boundary placeholder."""
    lat_delta = offset_km / KM_PER_DEGREE_LATITUDE
    lon_delta = offset_km / (KM_PER_DEGREE_LONGITUDE_AT_EQUATOR * cos(radians(lat)))
    return {
        "type": "Polygon",
        "coordinates": [[
            [lon - lon_delta, lat - lat_delta],
            [lon + lon_delta, lat - lat_delta],
            [lon + lon_delta, lat + lat_delta],
            [lon - lon_delta, lat + lat_delta],
            [lon - lon_delta, lat - lat_delta],
        ]],
    }


@router.get("/wards", response_model=list[WardResponse])
def list_wards() -> list[dict[str, object]]:
    """Every monitored ward with its current reading, band, and geometry."""
    return [
        {
            "ward_id": str(row.ward_id),
            "ward_name": str(row.ward_name),
            "aqi": int(row.aqi),
            "band": aqi_band(float(row.aqi)),
            "band_color": band_color(float(row.aqi)),
            "days_in_band": int(row.aqi_trend_days),
            "dominant_source": str(row.dominant_source),
            "latitude": float(row.latitude),
            "longitude": float(row.longitude),
            "geometry": _square_geometry(float(row.latitude), float(row.longitude)),
        }
        for _, row in WARD_STATE.iterrows()
    ]
