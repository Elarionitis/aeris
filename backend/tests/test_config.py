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
    # Anthropic wins when several keys are configured.
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
