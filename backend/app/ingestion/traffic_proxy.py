from __future__ import annotations

import json
from datetime import date, datetime, time as datetime_time, timedelta
from pathlib import Path
from typing import Iterable

import pandas as pd

from app.ingestion._base import (
    RAW_DATA_ROOT,
    IngestionContext,
    as_frame,
    bbox_area_km2,
    date_key,
    haversine_km,
    load_parquet,
    parse_date,
    parse_datetime,
    save_parquet,
    simple_polygon_bounds,
    ward_bucket,
)
from app.ingestion.landuse_loader import LANDUSE_PATH, LandUseLoader


ROAD_TAGS = "motorway|trunk|primary|secondary|tertiary|residential|unclassified|service|living_street"


class TrafficProxy:
    def __init__(self, cache_root: Path | None = None, session=None, landuse_path: Path | None = None) -> None:
        self.context = IngestionContext.create(cache_root or (RAW_DATA_ROOT / "traffic"), session=session)
        self.base_url = "https://overpass-api.de/api/interpreter"
        self.landuse_path = landuse_path or LANDUSE_PATH
        self.landuse_loader = LandUseLoader(cache_path=self.landuse_path, session=session)

    def _time_multiplier(self, hour: int) -> float:
        if 7 <= hour <= 10:
            return 1.6
        if 17 <= hour <= 20:
            return 1.8
        if 11 <= hour <= 16:
            return 1.15
        if 21 <= hour <= 23:
            return 0.75
        return 0.55

    def _road_density_for_feature(self, feature: dict[str, object]) -> float:
        geometry = feature.get("geometry", {})
        if geometry.get("type") != "Polygon" or not geometry.get("coordinates"):
            return 0.0
        bounds = simple_polygon_bounds(geometry["coordinates"])
        area_km2 = bbox_area_km2(bounds)
        min_lon, min_lat, max_lon, max_lat = bounds
        query = f"""
        [out:json][timeout:120];
        way["highway"]({min_lat},{min_lon},{max_lat},{max_lon});
        out geom;
        """
        response = self.context.session.get(self.base_url, params={"data": query}, timeout=30)
        response.raise_for_status()
        payload = response.json()
        road_km = 0.0
        for element in payload.get("elements", []):
            geometry_points = element.get("geometry", [])
            for start, end in zip(geometry_points, geometry_points[1:]):
                road_km += haversine_km(start["lat"], start["lon"], end["lat"], end["lon"])
        return road_km / area_km2 if area_km2 else 0.0

    def fetch(
        self,
        start_date: str | date | datetime,
        end_date: str | date | datetime,
        wards: Iterable[str] | None = None,
    ) -> pd.DataFrame:
        start = parse_date(start_date)
        end = parse_date(end_date)
        ward_filter = set(ward_bucket(list(wards) if wards is not None else None, "bengaluru"))
        landuse_frame = self.landuse_loader.fetch(start, end, wards=wards)
        if landuse_frame.empty:
            return as_frame([])

        cache_key = f"{date_key(start)}_{date_key(end)}"
        cached = load_parquet(self.context.cache_root, cache_key)
        if cached is not None:
            return cached

        geojson = json.loads(Path(self.landuse_path).read_text()) if Path(self.landuse_path).exists() else {"features": []}
        feature_map = {str(feature.get("properties", {}).get("ward_id")): feature for feature in geojson.get("features", [])}
        rows = []
        current = start
        while current <= end:
            for ward_id in landuse_frame["ward_id"].astype(str).tolist():
                if ward_id not in ward_filter:
                    continue
                feature = feature_map.get(ward_id)
                if feature is None:
                    continue
                base_density = self._road_density_for_feature(feature)
                for hour in range(24):
                    timestamp = pd.Timestamp(datetime.combine(current, datetime_time(hour=hour), tzinfo=pd.Timestamp.now(tz="UTC").tz))
                    rows.append(
                        {
                            "ward_id": ward_id,
                            "timestamp": timestamp,
                            "metric": "traffic_density_index",
                            "value": round(base_density * self._time_multiplier(hour), 4),
                            "source": "traffic_proxy",
                        }
                    )
            current += timedelta(days=1)

        frame = as_frame(rows)
        save_parquet(frame, self.context.cache_root, cache_key)
        return frame.reset_index(drop=True)
