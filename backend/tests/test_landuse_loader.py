import json

from app.ingestion.landuse_loader import LandUseLoader


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
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [[[77.58, 12.96], [77.60, 12.96], [77.60, 12.98], [77.58, 12.98], [77.58, 12.96]]],
                        },
                        "properties": {"name": "Ward A"},
                    }
                ],
            }
        )


def test_landuse_loader_writes_geojson_and_returns_schema(tmp_path):
    cache_path = tmp_path / "bengaluru_wards.geojson"
    client = LandUseLoader(cache_path=cache_path, session=FakeSession())
    frame = client.fetch("2026-07-20", "2026-07-20", wards=["Ward A"])

    assert frame.iloc[0]["metric"] == "landuse_classification"
    assert cache_path.exists()
    payload = json.loads(cache_path.read_text())
    assert payload["features"][0]["properties"]["ward_id"] == "Ward A"
