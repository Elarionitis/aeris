from __future__ import annotations

import csv
import os
from datetime import date, datetime
from io import StringIO
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


BENGALURU_BBOX = (77.35, 12.80, 77.75, 13.20)


class FirmsClient:
    def __init__(self, cache_root: Path | None = None, session=None) -> None:
        self.context = IngestionContext.create(cache_root or (RAW_DATA_ROOT / "firms"), session=session)
        self.map_key = os.getenv("FIRMS_MAP_KEY", "")
        self.product = os.getenv("FIRMS_PRODUCT", "VIIRS_SNPP_NRT")
        self.base_url = os.getenv("FIRMS_API_BASE", "https://firms.modaps.eosdis.nasa.gov/api")

    def _request_csv(self, start_date: date, end_date: date) -> str:
        if not self.map_key:
            raise ValueError("FIRMS_MAP_KEY is required")
        days = max((end_date - start_date).days + 1, 1)
        bbox = ",".join(str(value) for value in BENGALURU_BBOX)
        url = f"{self.base_url}/area/csv/{self.map_key}/{self.product}/{bbox}/{days}"
        response = retry_request(self.context.session, "GET", url)
        return response.text

    def _parse_rows(self, csv_text: str, wards: list[str]) -> list[dict[str, object]]:
        reader = csv.DictReader(StringIO(csv_text))
        rows: list[dict[str, object]] = []
        for item in reader:
            dt_value = item.get("acq_date")
            time_value = item.get("acq_time", "0000")
            timestamp = parse_datetime(f"{dt_value} {time_value.zfill(4)[:2]}:{time_value.zfill(4)[2:]}:00+00:00")
            value = item.get("frp") or item.get("bright_ti4") or 1.0
            for ward_id in wards:
                rows.append(
                    {
                        "ward_id": ward_id,
                        "timestamp": timestamp,
                        "metric": "fire_hotspot",
                        "value": float(value),
                        "source": "firms",
                    }
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
        cached = load_parquet(self.context.cache_root, f"{date_key(start)}_{date_key(end)}")
        if cached is not None:
            return cached
        csv_text = self._request_csv(start, end)
        frame = as_frame(self._parse_rows(csv_text, ward_ids))
        save_parquet(frame, self.context.cache_root, f"{date_key(start)}_{date_key(end)}")
        return frame.reset_index(drop=True)
