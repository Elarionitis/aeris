from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Iterable

import pandas as pd

from app.ingestion._base import (
    RAW_DATA_ROOT,
    IngestionContext,
    as_frame,
    date_key,
    daterange,
    load_parquet,
    normalize_wards,
    parse_date,
    parse_datetime,
    retry_request,
    save_parquet,
)


SUPPORTED_PARAMETERS = {"aqi", "pm25", "pm10", "no2", "so2"}


class OpenAQClient:
    def __init__(self, cache_root: Path | None = None, session=None) -> None:
        self.context = IngestionContext.create(cache_root or (RAW_DATA_ROOT / "openaq"), session=session)
        self.base_url = "https://api.openaq.org/v3"

    def _fetch_day(self, day: date, wards: list[str] | None) -> pd.DataFrame:
        cached = load_parquet(self.context.cache_root, date_key(day))
        if cached is not None:
            return cached

        records: list[dict[str, object]] = []
        page = 1
        limit = 1000
        while True:
            response = retry_request(
                self.context.session,
                "GET",
                f"{self.base_url}/measurements",
                params={
                    "country": "IN",
                    "city": "Bengaluru",
                    "date_from": day.isoformat(),
                    "date_to": day.isoformat(),
                    "limit": limit,
                    "page": page,
                    "sort": "desc",
                },
            )
            payload = response.json()
            results = payload.get("results", [])
            for item in results:
                parameter = str(item.get("parameter", "")).lower()
                if parameter not in SUPPORTED_PARAMETERS:
                    continue
                ward_id = str(item.get("location") or item.get("station") or item.get("name") or "bengaluru")
                if wards is not None and ward_id not in wards:
                    continue
                timestamp = parse_datetime(item.get("date", {}).get("utc") or item.get("datetime") or item.get("date"))
                records.append(
                    {
                        "ward_id": ward_id,
                        "timestamp": timestamp,
                        "metric": parameter,
                        "value": item.get("value"),
                        "source": "openaq",
                    }
                )
            if len(results) < limit:
                break
            page += 1

        frame = as_frame(records)
        save_parquet(frame, self.context.cache_root, date_key(day))
        return frame

    def fetch(
        self,
        start_date: str | date | datetime,
        end_date: str | date | datetime,
        wards: Iterable[str] | None = None,
    ) -> pd.DataFrame:
        start = parse_date(start_date)
        end = parse_date(end_date)
        ward_filter = normalize_wards(wards)
        frames = [self._fetch_day(day, ward_filter) for day in daterange(start, end)]
        if not frames:
            return as_frame([])
        combined = pd.concat(frames, ignore_index=True) if len(frames) > 1 else frames[0]
        if ward_filter is not None:
            combined = combined[combined["ward_id"].isin(ward_filter)]
        return combined.reset_index(drop=True)
