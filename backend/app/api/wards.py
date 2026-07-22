from __future__ import annotations

from math import cos, radians

from fastapi import APIRouter
from pydantic import BaseModel

from app.models.enforcement import WARD_STATE, aqi_band


router = APIRouter(tags=["wards"])


class WardGeometry(BaseModel):
    type: str
    coordinates: list


class WardResponse(BaseModel):
    ward_id: str
    ward_name: str
    aqi: int
    band: str
    latitude: float
    longitude: float
    geometry: dict


def _square_geometry(lat: float, lon: float, offset_km: float = 0.9) -> dict[str, object]:
    lat_delta = offset_km / 110.574
    lon_delta = offset_km / (111.320 * cos(radians(lat)))
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
    wards: list[dict[str, object]] = []
    for _, row in WARD_STATE.iterrows():
        wards.append(
            {
                "ward_id": str(row.ward_id),
                "ward_name": str(row.ward_name),
                "aqi": int(row.aqi),
                "band": aqi_band(float(row.aqi)),
                "latitude": float(row.latitude),
                "longitude": float(row.longitude),
                "geometry": _square_geometry(float(row.latitude), float(row.longitude)),
            }
        )
    return wards
