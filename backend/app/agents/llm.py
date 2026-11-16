"""Provider-agnostic chat-model factory.

The orchestrator and the advisory agent share one LLM configuration. Any of
Anthropic, OpenAI, or Google Gemini can back it; whichever provider has a key
present is used when ``LLM_PROVIDER=auto``. When no key is configured the
factory returns ``None`` and callers fall back to their deterministic path, so
the service stays fully functional offline.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from app.core.config import Settings, get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class LLMInfo:
    """What the running process actually resolved for the LLM."""

    provider: str
    model: str
    available: bool

    @property
    def mode(self) -> str:
        return "llm" if self.available else "deterministic"

    def as_dict(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "model": self.model or None,
            "available": self.available,
            "mode": self.mode,
        }


def message_text(message: object) -> str:
    """Extract plain text from a chat message across LangChain versions.

    ``AIMessage.text`` is a property in langchain-core 1.x and was a method
    before it; ``content`` can also be a list of content blocks.
    """
    value = getattr(message, "text", None)
    if isinstance(value, str):
        return value.strip()
    if callable(value):
        try:
            return str(value()).strip()
        except Exception:
            pass
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = [
            block.get("text", "") if isinstance(block, dict) else str(block)
            for block in content
        ]
        return " ".join(part for part in parts if part).strip()
    return str(content).strip()


def llm_info(settings: Settings | None = None) -> LLMInfo:
    settings = settings or get_settings()
    provider = settings.resolved_llm_provider()
    if provider == "none":
        return LLMInfo(provider="none", model="", available=False)
    return LLMInfo(provider=provider, model=settings.resolved_llm_model(provider), available=True)


def _build(provider: str, model: str, settings: Settings):
    """Instantiate the LangChain chat model for ``provider``."""
    common = {
        "model": model,
        "temperature": settings.llm_temperature,
        "timeout": settings.llm_timeout_seconds,
        "max_retries": 2,
    }
    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            api_key=settings.anthropic_api_key,
            max_tokens=settings.llm_max_tokens,
            **common,
        )
    if provider == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            api_key=settings.openai_api_key,
            max_completion_tokens=settings.llm_max_tokens,
            **common,
        )
    if provider == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=model,
            google_api_key=settings.google_api_key,
            temperature=settings.llm_temperature,
            max_output_tokens=settings.llm_max_tokens,
            timeout=settings.llm_timeout_seconds,
            max_retries=2,
        )
    raise ValueError(f"Unsupported LLM provider: {provider}")


@lru_cache(maxsize=1)
def get_chat_model():
    """Return a cached chat model, or ``None`` when no provider is configured."""
    settings = get_settings()
    info = llm_info(settings)
    if not info.available:
        logger.info(
            "No LLM provider configured; orchestrator and advisory will use deterministic planning"
        )
        return None
    try:
        model = _build(info.provider, info.model, settings)
    except Exception:
        logger.exception("Failed to initialise LLM provider %s (%s)", info.provider, info.model)
        return None
    logger.info("LLM ready: provider=%s model=%s", info.provider, info.model)
    return model


def reset_chat_model_cache() -> None:
    """Drop the cached model; used by tests and after a settings change."""
    get_chat_model.cache_clear()
