from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable

import pandas as pd

from app.ingestion._base import (
    PROJECT_ROOT,
    RAW_DATA_ROOT,
    IngestionContext,
    as_frame,
    ensure_directory,
    parse_date,
    retry_request,
)


LANDUSE_PATH = RAW_DATA_ROOT / "landuse" / "bengaluru_wards.geojson"


def _ward_classification(name: str, area_km2: float | None = None) -> str:
    lowered = name.lower()
    if any(token in lowered for token in ["industrial", "factory", "plant"]):
        return "industrial"
    if any(token in lowered for token in ["mall", "market", "commercial", "business"]):
        return "commercial"
    if any(token in lowered for token in ["park", "lake", "green", "garden"]):
        return "green"
    if area_km2 is not None and area_km2 < 1.5:
        return "commercial"
    digest = hashlib.sha1(name.encode("utf-8")).hexdigest()
    return ["residential", "commercial", "industrial", "green"][int(digest[:2], 16) % 4]


class LandUseLoader:
    def __init__(self, cache_path: Path | None = None, session=None) -> None:
        self.context = IngestionContext.create((cache_path or LANDUSE_PATH).parent, session=session)
        self.cache_path = cache_path or LANDUSE_PATH
        self.base_url = "https://overpass-api.de/api/interpreter"

    def _fetch_geojson(self) -> dict[str, object]:
        query = """
        [out:json][timeout:180];
        relation["boundary"="administrative"]["admin_level"="10"]
          ["name"~"Bengaluru|Bangalore",i];
        out geom;
        """
        response = retry_request(self.context.session, "GET", self.base_url, params={"data": query})
        payload = response.json()
        if payload.get("type") == "FeatureCollection":
            return payload
        features: list[dict[str, object]] = []
        for element in payload.get("elements", []):
            geometry = element.get("geometry")
            if not geometry:
                continue
            features.append(
                {
                    "type": "Feature",
                    "geometry": {"type": "Polygon", "coordinates": [
                        [[point["lon"], point["lat"]] for point in geometry]
                    ]},
                    "properties": {"name": element.get("tags", {}).get("name", f"ward-{element.get('id')}")},
                }
            )
        return {"type": "FeatureCollection", "features": features}

    def _annotate(self, geojson: dict[str, object]) -> dict[str, object]:
        features = []
        for feature in geojson.get("features", []):
            properties = dict(feature.get("properties", {}))
            geometry = feature.get("geometry", {})
            name = str(properties.get("name") or properties.get("ward_id") or "unknown")
            bounds = None
            if geometry.get("type") == "Polygon" and geometry.get("coordinates"):
                xs = [pt[0] for pt in geometry["coordinates"][0]]
                ys = [pt[1] for pt in geometry["coordinates"][0]]
                area_km2 = max((max(xs) - min(xs)) * (max(ys) - min(ys)) * 123.0, 0.01)
                bounds = (min(xs), min(ys), max(xs), max(ys))
            else:
                area_km2 = 1.0
            properties["ward_id"] = name
            properties["land_use"] = _ward_classification(name, area_km2)
            if bounds is not None:
                properties["bbox"] = list(bounds)
            features.append({"type": "Feature", "geometry": geometry, "properties": properties})
        return {"type": "FeatureCollection", "features": features}

    def fetch(
        self,
        start_date: str | date | datetime,
        end_date: str | date | datetime,
        wards: Iterable[str] | None = None,
    ) -> pd.DataFrame:
        _ = parse_date(start_date)
        _ = parse_date(end_date)
        cache_file = Path(self.cache_path)
        ensure_directory(cache_file.parent)
        if cache_file.exists():
            geojson = json.loads(cache_file.read_text())
        else:
            geojson = self._annotate(self._fetch_geojson())
            cache_file.write_text(json.dumps(geojson, indent=2))

        ward_filter = {str(item).strip() for item in wards} if wards is not None else None
        rows = []
        for feature in geojson.get("features", []):
            properties = feature.get("properties", {})
            ward_id = str(properties.get("ward_id") or properties.get("name") or "unknown")
            if ward_filter is not None and ward_id not in ward_filter:
                continue
            rows.append(
                {
                    "ward_id": ward_id,
                    "timestamp": pd.Timestamp.now(tz=timezone.utc),
                    "metric": "landuse_classification",
                    "value": properties.get("land_use", "residential"),
                    "source": "landuse",
                }
            )
        return as_frame(rows)
