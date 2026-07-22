import json

from app.ingestion.traffic_proxy import TrafficProxy


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload
        self.status_code = 200

    def json(self):
        return self._payload

    def raise_for_status(self):
        return None


class FakeSession:
    def __init__(self):
        self.landuse_calls = 0

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
                        "properties": {"name": "Ward A", "ward_id": "Ward A", "land_use": "residential"},
                    }
                ],
            }
        )

    def get(self, url, params=None, timeout=None):
        return FakeResponse(
            {
                "elements": [
                    {
                        "geometry": [
                            {"lat": 12.96, "lon": 77.58},
                            {"lat": 12.97, "lon": 77.59},
                            {"lat": 12.98, "lon": 77.60},
                        ]
                    }
                ]
            }
        )


def test_traffic_proxy_uses_time_multiplier_and_road_density(tmp_path):
    landuse_path = tmp_path / "bengaluru_wards.geojson"
    landuse_path.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [[[77.58, 12.96], [77.60, 12.96], [77.60, 12.98], [77.58, 12.98], [77.58, 12.96]]],
                        },
                        "properties": {"ward_id": "Ward A", "name": "Ward A", "land_use": "residential"},
                    }
                ],
            }
        )
    )
    client = TrafficProxy(cache_root=tmp_path / "traffic", session=FakeSession(), landuse_path=landuse_path)
    frame = client.fetch("2026-07-20", "2026-07-20", wards=["Ward A"])

    assert frame["metric"].unique().tolist() == ["traffic_density_index"]
    assert frame["ward_id"].unique().tolist() == ["Ward A"]
