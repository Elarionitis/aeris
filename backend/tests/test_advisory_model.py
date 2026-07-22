import json

from app.models import advisory as advisory_module


def test_advisory_response_caches_and_returns_disclaimer(tmp_path, monkeypatch):
    monkeypatch.setattr(advisory_module, "ADVISORY_CACHE_DIR", tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    first = advisory_module.generate_advisory_response("BTM", language="kn")
    second = advisory_module.generate_advisory_response("BTM", language="kn")
    assert first["disclaimer"]
    assert first["delivery_channels"] == ["app_push", "led_display", "ivr_script"]
    assert second["advisory"] == first["advisory"]
    cache_files = list(tmp_path.glob("*.json"))
    assert cache_files
    cached = json.loads(cache_files[0].read_text())
    assert cached["response"]["ward_id"] == "BTM"
