from app.ingestion.weather_client import WeatherClient


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload
        self.status_code = 200

    def json(self):
        return self._payload

    def raise_for_status(self):
        return None


class FakeSession:
    def request(self, method, url, params=None, headers=None, timeout=None):
        return FakeResponse(
            {
                "hourly": [
                    {"dt": 1784505600, "wind_speed": 2.5, "wind_deg": 120, "temp": 30.1, "humidity": 60},
                    {"dt": 1784509200, "wind_speed": 3.0, "wind_deg": 130, "temp": 29.7, "humidity": 58},
                ]
            }
        )


def test_weather_fetch_returns_hourly_schema(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENWEATHER_API_KEY", "test")
    client = WeatherClient(cache_root=tmp_path, session=FakeSession())
    frame = client.fetch("2026-07-20", "2026-07-20", wards=["Ward A"])

    assert set(frame["metric"]) == {"wind_speed", "wind_direction", "temperature", "humidity"}
    assert frame["ward_id"].nunique() == 1
    assert (tmp_path / "2026-07-20.parquet").exists()
