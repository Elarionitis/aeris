from app.ingestion.firms_client import FirmsClient


class FakeResponse:
    def __init__(self, text):
        self.text = text
        self.status_code = 200

    def raise_for_status(self):
        return None


class FakeSession:
    def request(self, method, url, params=None, headers=None, timeout=None):
        return FakeResponse("latitude,longitude,acq_date,acq_time,frp\n12.97,77.59,2026-07-20,1230,7.5\n")


def test_firms_fetch_converts_csv_to_frame(tmp_path, monkeypatch):
    monkeypatch.setenv("FIRMS_MAP_KEY", "test")
    client = FirmsClient(cache_root=tmp_path, session=FakeSession())
    frame = client.fetch("2026-07-20", "2026-07-20", wards=["Ward A"])

    assert frame.iloc[0]["metric"] == "fire_hotspot"
    assert frame.iloc[0]["value"] == 7.5
    assert (tmp_path / "2026-07-20_2026-07-20.parquet").exists()
