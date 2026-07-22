from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator

import pandas as pd
import requests


PROJECT_ROOT = Path(__file__).resolve().parents[3]
RAW_DATA_ROOT = PROJECT_ROOT / "data" / "raw"
WARD_SCHEMA_COLUMNS = ["ward_id", "timestamp", "metric", "value", "source"]


def ensure_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def parse_date(value: str | date | datetime) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    return datetime.fromisoformat(str(value)).date()


def parse_datetime(value: Any) -> pd.Timestamp:
    if value is None:
        return pd.NaT
    if isinstance(value, pd.Timestamp):
        return value.tz_convert("UTC") if value.tzinfo else value.tz_localize("UTC")
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return pd.Timestamp(value).tz_convert("UTC")
    if isinstance(value, (int, float)):
        return pd.to_datetime(value, unit="s", utc=True)
    return pd.to_datetime(value, utc=True, errors="coerce")


def daterange(start_date: date, end_date: date) -> Iterator[date]:
    current = start_date
    while current <= end_date:
        yield current
        current += timedelta(days=1)


def date_key(value: date | datetime) -> str:
    return parse_date(value).isoformat()


def normalize_wards(wards: Iterable[str] | None) -> list[str] | None:
    if wards is None:
        return None
    cleaned = [str(item).strip() for item in wards if str(item).strip()]
    return cleaned or None


def as_frame(records: list[dict[str, Any]]) -> pd.DataFrame:
    frame = pd.DataFrame.from_records(records, columns=WARD_SCHEMA_COLUMNS)
    if frame.empty:
        return pd.DataFrame(columns=WARD_SCHEMA_COLUMNS)
    frame = frame.sort_values(["ward_id", "timestamp", "metric"], kind="stable")
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce")
    return frame.reset_index(drop=True)


def parquet_path(cache_dir: Path, key: str) -> Path:
    return ensure_directory(cache_dir) / f"{key}.parquet"


def save_parquet(frame: pd.DataFrame, cache_dir: Path, key: str) -> Path:
    path = parquet_path(cache_dir, key)
    frame.to_parquet(path, index=False)
    return path


def load_parquet(cache_dir: Path, key: str) -> pd.DataFrame | None:
    path = parquet_path(cache_dir, key)
    if not path.exists():
        return None
    return pd.read_parquet(path)


def retry_request(
    session: requests.Session,
    method: str,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 30,
    max_attempts: int = 4,
    backoff_seconds: float = 0.5,
) -> requests.Response:
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            response = session.request(method, url, params=params, headers=headers, timeout=timeout)
            if response.status_code >= 500 or response.status_code == 429:
                raise requests.HTTPError(f"retryable HTTP {response.status_code}", response=response)
            response.raise_for_status()
            return response
        except Exception as exc:  # pragma: no cover - exercised through retry behavior tests
            last_error = exc
            if attempt >= max_attempts:
                break
            time.sleep(backoff_seconds * (2 ** (attempt - 1)))
    assert last_error is not None
    raise last_error


def ward_bucket(wards: list[str] | None, fallback: str) -> list[str]:
    normalized = normalize_wards(wards)
    return normalized or [fallback]


def simple_polygon_bounds(coordinates: list[list[list[float]]]) -> tuple[float, float, float, float]:
    points = coordinates[0]
    longs = [point[0] for point in points]
    lats = [point[1] for point in points]
    return min(longs), min(lats), max(longs), max(lats)


def bbox_area_km2(bounds: tuple[float, float, float, float]) -> float:
    min_lon, min_lat, max_lon, max_lat = bounds
    lat_km = 110.574 * (max_lat - min_lat)
    lon_km = 111.320 * math.cos(math.radians((min_lat + max_lat) / 2)) * (max_lon - min_lon)
    return max(abs(lat_km * lon_km), 0.01)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return 2 * radius * math.asin(math.sqrt(a))


def utc_window(start_date: date, end_date: date) -> tuple[pd.Timestamp, pd.Timestamp]:
    start = pd.Timestamp(datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc))
    end = pd.Timestamp(datetime.combine(end_date, datetime.max.time(), tzinfo=timezone.utc))
    return start, end


@dataclass
class IngestionContext:
    cache_root: Path
    session: requests.Session

    @classmethod
    def create(cls, cache_root: Path, session: requests.Session | None = None) -> "IngestionContext":
        return cls(cache_root=ensure_directory(cache_root), session=session or requests.Session())
