from app.models.enforcement import build_priority_queue, priority_queue_response


def test_priority_queue_contains_coordinates_and_scores():
    frame = build_priority_queue(limit=3)
    assert list(frame.columns) == ["ward_id", "ward_name", "aqi", "aqi_band", "score", "dominant_source", "source_density_nearby", "source_coordinates", "recommendation"]
    assert frame.iloc[0]["score"] >= frame.iloc[1]["score"]
    assert frame.iloc[0]["source_coordinates"]


def test_priority_queue_response_has_disclaimer():
    response = priority_queue_response(limit=2)
    assert "disclaimer" in response
    assert len(response["items"]) == 2
