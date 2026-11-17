"""Tests for settings resolution and provider selection."""

from __future__ import annotations

from app.core.aqi import aqi_band, band_scale, severity_weight
from app.core.config import DEFAULT_MODELS, Settings


def _settings(**overrides) -> Settings:
    # _env_file=None isolates the test from a developer's local .env.
    return Settings(_env_file=None, **overrides)


def test_defaults_are_safe_without_any_env():
    settings = _settings()
    assert settings.environment == "development"
    assert settings.resolved_llm_provider() == "none"
    assert settings.allowed_origins == ["http://localhost:5173", "http://127.0.0.1:5173"]


def test_auto_provider_picks_whichever_key_is_present():
    assert _settings(openai_api_key="sk-test").resolved_llm_provider() == "openai"
    assert _settings(google_api_key="g-test").resolved_llm_provider() == "google"
    # Anthropic wins over OpenAI when both are configured.
    both = _settings(anthropic_api_key="a-test", openai_api_key="sk-test")
    assert both.resolved_llm_provider() == "anthropic"


def test_explicit_provider_without_a_key_degrades_to_none():
    assert _settings(llm_provider="openai").resolved_llm_provider() == "none"
    assert _settings(llm_provider="openai", openai_api_key="sk-test").resolved_llm_provider() == "openai"


def test_provider_none_ignores_configured_keys():
    settings = _settings(llm_provider="none", anthropic_api_key="a-test")
    assert settings.resolved_llm_provider() == "none"


def test_model_defaults_per_provider_and_override():
    settings = _settings(openai_api_key="sk-test")
    assert settings.resolved_llm_model() == DEFAULT_MODELS["openai"]
    assert _settings(openai_api_key="sk-test", llm_model="custom").resolved_llm_model() == "custom"


def test_production_disables_the_loose_localhost_regex():
    assert _settings().origin_regex is not None
    assert _settings(environment="production").origin_regex is None


def test_invalid_log_level_falls_back_to_info():
    assert _settings(log_level="loud").log_level == "INFO"
    assert _settings(log_level="debug").log_level == "DEBUG"


def test_origins_are_split_and_trimmed():
    settings = _settings(cors_allow_origins="https://a.example , https://b.example,")
    assert settings.allowed_origins == ["https://a.example", "https://b.example"]


def test_band_scale_is_continuous_and_ordered():
    bands = band_scale()
    assert bands[0]["lower"] == 0
    assert bands[-1]["upper"] is None
    for lower, upper in zip(bands, bands[1:]):
        assert lower["upper"] + 1 == upper["lower"]


def test_severity_weight_increases_with_aqi():
    weights = [severity_weight(value) for value in (25, 75, 150, 250, 350, 450)]
    assert weights == sorted(weights)


def test_band_edges():
    assert aqi_band(0) == "Good"
    assert aqi_band(50) == "Good"
    assert aqi_band(51) == "Satisfactory"
    assert aqi_band(100) == "Satisfactory"
    assert aqi_band(101) == "Moderate"
    assert aqi_band(10_000) == "Severe"
    # Negative readings are clamped rather than crashing the band lookup.
    assert aqi_band(-5) == "Good"


def test_groq_is_picked_up_by_auto():
    settings = _settings(groq_api_key="gsk-test")
    assert settings.resolved_llm_provider() == "groq"
    assert settings.resolved_llm_model() == DEFAULT_MODELS["groq"]


def test_every_provider_default_is_a_non_empty_model_id():
    """A retired or blank default fails every call at runtime.

    openai_compatible is the deliberate exception: its model id belongs to
    whichever endpoint LLM_BASE_URL names, so LLM_MODEL is required instead.
    """
    for provider, model in DEFAULT_MODELS.items():
        if provider == "openai_compatible":
            assert model == ""
            continue
        assert model, f"{provider} has no default model"
        assert " " not in model, f"{provider} default looks malformed: {model!r}"


def test_openai_compatible_needs_both_url_and_key():
    # A key with no endpoint, or an endpoint with no key, is not configured.
    assert _settings(llm_api_key="hf-test").resolved_llm_provider() == "none"
    assert _settings(llm_base_url="https://router.huggingface.co/v1").resolved_llm_provider() == "none"
    both = _settings(llm_api_key="hf-test", llm_base_url="https://router.huggingface.co/v1")
    assert both.resolved_llm_provider() == "openai_compatible"


def test_auto_prefers_groq_over_everything_else():
    """Groq leads the auto order; Gemini's free tier is too flaky to default to."""
    settings = _settings(
        groq_api_key="gsk-test",
        google_api_key="g-test",
        anthropic_api_key="a-test",
        llm_api_key="hf-test",
        llm_base_url="https://router.huggingface.co/v1",
    )
    assert settings.resolved_llm_provider() == "groq"


def test_google_is_last_in_the_auto_order():
    from app.core.config import AUTO_PROVIDER_ORDER

    assert AUTO_PROVIDER_ORDER[0] == "groq"
    assert AUTO_PROVIDER_ORDER[-1] == "google"
    # An explicit choice still wins over the ordering.
    assert _settings(llm_provider="google", google_api_key="g").resolved_llm_provider() == "google"


def test_known_openai_compatible_endpoints_are_https_v1():
    from app.core.config import OPENAI_COMPATIBLE_ENDPOINTS

    assert "huggingface" in OPENAI_COMPATIBLE_ENDPOINTS
    for name, url in OPENAI_COMPATIBLE_ENDPOINTS.items():
        assert url.startswith("https://"), name
        assert url.endswith("/v1"), name
