import json

from app.models import advisory as advisory_module


def test_advisory_response_caches_and_returns_disclaimer(tmp_path, monkeypatch):
    monkeypatch.setattr(advisory_module, "ADVISORY_CACHE_DIR", tmp_path)
    first = advisory_module.generate_advisory_response("BTM", language="kn")
    second = advisory_module.generate_advisory_response("BTM", language="kn")

    assert first["disclaimer"]
    assert first["advisory_source"] in {"llm", "template"}
    assert first["delivery_channels"] == ["app_push", "led_display", "ivr_script"]
    assert second["advisory"] == first["advisory"]

    cache_files = list(tmp_path.glob("*.json"))
    assert cache_files
    cached = json.loads(cache_files[0].read_text(encoding="utf-8"))
    assert cached["response"]["ward_id"] == "BTM"


def test_advisory_falls_back_to_template_when_llm_unavailable(tmp_path, monkeypatch):
    monkeypatch.setattr(advisory_module, "ADVISORY_CACHE_DIR", tmp_path)
    monkeypatch.setattr("app.agents.llm.get_chat_model", lambda: None)

    response = advisory_module.generate_advisory_response("Jayanagar", language="en")

    assert response["advisory_source"] == "template"
    assert "Jayanagar" in response["advisory"]


def test_advisory_rejects_unsafe_llm_output(tmp_path, monkeypatch):
    monkeypatch.setattr(advisory_module, "ADVISORY_CACHE_DIR", tmp_path)

    class UnsafeModel:
        def invoke(self, _messages):
            class Reply:
                content = "Take 500 mg of medication twice daily and stay indoors."

                def text(self):
                    return self.content

            return Reply()

    monkeypatch.setattr("app.agents.llm.get_chat_model", lambda: UnsafeModel())

    response = advisory_module.generate_advisory_response("HSR", language="en")

    # The safety filter must drop dosage language and fall back to the template.
    assert response["advisory_source"] == "template"
    assert "mg" not in response["advisory"]


def test_unknown_language_falls_back_to_english():
    assert advisory_module.normalise_language("zz") == "en"
    assert advisory_module.normalise_language(None) == "en"
    assert advisory_module.normalise_language("TA") == "ta"
