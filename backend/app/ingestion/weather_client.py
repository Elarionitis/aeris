from __future__ import annotations

import os
from datetime import date, datetime, time as datetime_time, timezone
from pathlib import Path
from typing import Iterable

import pandas as pd

from app.ingestion._base import (
    RAW_DATA_ROOT,
    IngestionContext,
    as_frame,
    date_key,
    load_parquet,
    normalize_wards,
    parse_date,
    parse_datetime,
    retry_request,
    save_parquet,
    ward_bucket,
)


BENGALURU_COORDS = (12.9716, 77.5946)


class WeatherClient:
    def __init__(self, cache_root: Path | None = None, session=None) -> None:
        self.context = IngestionContext.create(cache_root or (RAW_DATA_ROOT / "weather"), session=session)
        self.provider = os.getenv("AQI_WEATHER_PROVIDER", "openweather").lower()
        self.api_key = os.getenv("OPENWEATHER_API_KEY", "")
        self.imd_url = os.getenv("IMD_WEATHER_URL", "")
        self.imd_api_key = os.getenv("IMD_API_KEY", "")

    def _request_weather(self, timestamp: pd.Timestamp | None = None) -> dict[str, object]:
        if self.provider == "imd" and self.imd_url:
            response = retry_request(
                self.context.session,
                "GET",
                self.imd_url,
                params={"api_key": self.imd_api_key} if self.imd_api_key else None,
            )
            return response.json()

        lat, lon = BENGALURU_COORDS
        if not self.api_key:
            raise ValueError("OPENWEATHER_API_KEY is required when AQI_WEATHER_PROVIDER is not set to imd")
        params = {"lat": lat, "lon": lon, "appid": self.api_key, "units": "metric"}
        response = retry_request(
            self.context.session,
            "GET",
            "https://api.openweathermap.org/data/3.0/onecall",
            params=params,
        )
        return response.json()

    def _hourly_rows(self, payload: dict[str, object], wards: list[str]) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        hourly = payload.get("hourly", []) if isinstance(payload, dict) else []
        for hour in hourly:
            timestamp = parse_datetime(hour.get("dt"))
            for ward_id in wards:
                rows.extend(
                    [
                        {
                            "ward_id": ward_id,
                            "timestamp": timestamp,
                            "metric": "wind_speed",
                            "value": hour.get("wind_speed"),
                            "source": "weather",
                        },
                        {
                            "ward_id": ward_id,
                            "timestamp": timestamp,
                            "metric": "wind_direction",
                            "value": hour.get("wind_deg"),
                            "source": "weather",
                        },
                        {
                            "ward_id": ward_id,
                            "timestamp": timestamp,
                            "metric": "temperature",
                            "value": hour.get("temp"),
                            "source": "weather",
                        },
                        {
                            "ward_id": ward_id,
                            "timestamp": timestamp,
                            "metric": "humidity",
                            "value": hour.get("humidity"),
                            "source": "weather",
                        },
                    ]
                )
        return rows

    def fetch(
        self,
        start_date: str | date | datetime,
        end_date: str | date | datetime,
        wards: Iterable[str] | None = None,
    ) -> pd.DataFrame:
        start = parse_date(start_date)
        end = parse_date(end_date)
        ward_ids = ward_bucket(list(wards) if wards is not None else None, "bengaluru")
        cached = load_parquet(self.context.cache_root, date_key(start))
        if cached is not None and start == end:
            return cached

        payload = self._request_weather()
        rows = self._hourly_rows(payload, ward_ids)
        frame = as_frame(rows)
        if not frame.empty:
            start_ts = pd.Timestamp(datetime.combine(start, datetime_time.min, tzinfo=timezone.utc))
            end_ts = pd.Timestamp(datetime.combine(end, datetime_time.max, tzinfo=timezone.utc))
            frame = frame[(frame["timestamp"] >= start_ts) & (frame["timestamp"] <= end_ts)]
        save_parquet(frame, self.context.cache_root, date_key(start))
        return frame.reset_index(drop=True)
