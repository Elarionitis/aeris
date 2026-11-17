"""Typed application settings loaded from the environment and ``.env``.

Every tunable value in the service is declared here so deployments can be
configured without code changes. ``get_settings`` is cached, so the ``.env``
file is parsed once per process.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_ROOT.parent

LLMProvider = Literal[
    "auto", "anthropic", "openai", "google", "groq", "openai_compatible", "none"
]

#: Default model per provider. Providers retire model ids, and a retired id
#: fails every request, so these are pinned to current releases and should be
#: reviewed when a provider deprecates one. Override with LLM_MODEL.
DEFAULT_MODELS: dict[str, str] = {
    "anthropic": "claude-sonnet-5-5",
    "openai": "gpt-4o-mini",
    "google": "gemini-3.8-flash",
    "groq": "openai/gpt-oss-120b",
    # openai_compatible has no sensible default: the model id belongs to
    # whichever endpoint LLM_BASE_URL points at. LLM_MODEL is required.
    "openai_compatible": "",
}

#: Order LLM_PROVIDER=auto tries providers in.
#:
#: Groq leads because its free tier is the most dependable way to get a
#: working orchestrator with no spend, and tool calling is the one capability
#: this project cannot do without. Google trails because its free tier returns
#: 503 under load often enough to be unusable for a public demo; set
#: LLM_PROVIDER=google explicitly if you want it anyway.
AUTO_PROVIDER_ORDER: tuple[str, ...] = (
    "groq",
    "anthropic",
    "openai",
    "openai_compatible",
    "google",
)

#: Ready-made LLM_BASE_URL values for providers that speak the OpenAI API.
#: Any of these works with LLM_PROVIDER=openai_compatible.
OPENAI_COMPATIBLE_ENDPOINTS: dict[str, str] = {
    "groq": "https://api.groq.com/openai/v1",
    "huggingface": "https://router.huggingface.co/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "cerebras": "https://api.cerebras.ai/v1",
    "together": "https://api.together.xyz/v1",
}


class Settings(BaseSettings):
    """Runtime configuration for the AQI Intelligence API."""

    model_config = SettingsConfigDict(
        env_file=(BACKEND_ROOT / ".env", PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Service -------------------------------------------------------
    app_name: str = "AQI Intelligence API"
    app_version: str = "1.0.0"
    environment: Literal["development", "staging", "production"] = "development"
    log_level: str = "INFO"
    log_format: Literal["text", "json"] = "text"

    # --- HTTP ----------------------------------------------------------
    cors_allow_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    cors_allow_origin_regex: str = r"https?://(localhost|127\.0\.0\.1)(:\d+)?$"
    request_timeout_seconds: int = 30

    # --- Models --------------------------------------------------------
    auto_train_on_startup: bool = True
    enable_prophet_baseline: bool = False
    forecast_horizon_hours: int = Field(default=72, ge=1, le=168)
    advisory_cache_ttl_seconds: int = Field(default=3600, ge=0)

    # --- Upstream data providers ---------------------------------------
    openweather_api_key: str = ""
    firms_map_key: str = ""
    openaq_api_key: str = ""
    imd_weather_url: str = ""
    imd_api_key: str = ""

    # --- LLM / orchestrator --------------------------------------------
    llm_provider: LLMProvider = "auto"
    llm_model: str = ""
    llm_temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    llm_max_tokens: int = Field(default=1024, ge=64, le=8192)
    llm_timeout_seconds: int = Field(default=45, ge=5, le=300)
    orchestrator_max_steps: int = Field(default=8, ge=1, le=30)
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    google_api_key: str = ""
    groq_api_key: str = ""

    # Any OpenAI-compatible endpoint: Hugging Face, OpenRouter, Cerebras,
    # Together, or a self-hosted gateway. See OPENAI_COMPATIBLE_ENDPOINTS.
    llm_base_url: str = ""
    llm_api_key: str = ""

    @field_validator("log_level", mode="before")
    @classmethod
    def _normalise_log_level(cls, value: object) -> str:
        level = str(value or "INFO").upper()
        if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            return "INFO"
        return level

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allow_origins.split(",") if origin.strip()]

    @property
    def origin_regex(self) -> str | None:
        """Loose localhost matching is a development convenience only."""
        if self.is_production:
            return None
        return self.cors_allow_origin_regex or None

    def resolved_llm_provider(self) -> str:
        """Pick the provider to use, honouring ``auto`` and available keys."""
        if self.llm_provider == "none":
            return "none"
        if self.llm_provider != "auto":
            return self.llm_provider if self.api_key_for(self.llm_provider) else "none"
        for candidate in AUTO_PROVIDER_ORDER:
            if self.api_key_for(candidate):
                return candidate
        return "none"

    def api_key_for(self, provider: str) -> str:
        """The key configured for ``provider``, or "" when it is unusable.

        An OpenAI-compatible endpoint needs a base URL as well as a key, so it
        only counts as configured when both are present.
        """
        if provider == "openai_compatible":
            return self.llm_api_key if self.llm_base_url and self.llm_api_key else ""
        return {
            "anthropic": self.anthropic_api_key,
            "openai": self.openai_api_key,
            "google": self.google_api_key,
            "groq": self.groq_api_key,
        }.get(provider, "")

    def resolved_llm_model(self, provider: str | None = None) -> str:
        provider = provider or self.resolved_llm_provider()
        if self.llm_model:
            return self.llm_model
        return DEFAULT_MODELS.get(provider, "")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    return Settings()
