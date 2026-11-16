from app.core.aqi import aqi_band
from app.models.enforcement import build_priority_queue, priority_queue_response

EXPECTED_COLUMNS = [
    "ward_id", "ward_name", "aqi", "aqi_band", "score", "dominant_source",
    "source_density_nearby", "source_coordinates", "recommendation",
]


def test_priority_queue_contains_coordinates_and_scores():
    frame = build_priority_queue(limit=3)
    assert list(frame.columns) == EXPECTED_COLUMNS
    assert frame.iloc[0]["score"] >= frame.iloc[1]["score"]
    assert frame.iloc[0]["source_coordinates"]


def test_priority_queue_response_has_disclaimer_and_method():
    response = priority_queue_response(limit=2)
    assert response["disclaimer"]
    assert response["method"]
    assert len(response["items"]) == 2


def test_queue_is_sorted_and_limited():
    frame = build_priority_queue(limit=50)
    scores = frame["score"].tolist()
    assert scores == sorted(scores, reverse=True)
    assert len(build_priority_queue(limit=1)) == 1


def test_bands_follow_cpcb_scale():
    assert aqi_band(40) == "Good"
    assert aqi_band(90) == "Satisfactory"
    assert aqi_band(168) == "Moderate"
    assert aqi_band(250) == "Poor"
    assert aqi_band(350) == "Very Poor"
    assert aqi_band(450) == "Severe"
