"""Provider-agnostic chat-model factory.

The orchestrator and the advisory agent share one LLM configuration. Any of
Anthropic, OpenAI, or Google Gemini can back it; whichever provider has a key
present is used when ``LLM_PROVIDER=auto``. When no key is configured the
factory returns ``None`` and callers fall back to their deterministic path, so
the service stays fully functional offline.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from functools import lru_cache

from app.core.config import Settings, get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


# Outcome of the most recent real call to the provider. A configured key says
# nothing about whether the provider actually answers: a retired model id or an
# overloaded endpoint fails every request while the service still reports a
# provider as "available". Health has to reflect calls, not configuration.
_OUTCOME_LOCK = threading.Lock()
_LAST_ERROR: str | None = None
_LAST_ERROR_AT: float | None = None
_LAST_SUCCESS_AT: float | None = None


def record_llm_success() -> None:
    """Note that a provider call succeeded, clearing any previous failure."""
    global _LAST_ERROR, _LAST_ERROR_AT, _LAST_SUCCESS_AT
    with _OUTCOME_LOCK:
        _LAST_ERROR = None
        _LAST_ERROR_AT = None
        _LAST_SUCCESS_AT = time.time()


def record_llm_failure(error: BaseException | str) -> None:
    """Note that a provider call failed, keeping a short reason for /health."""
    global _LAST_ERROR, _LAST_ERROR_AT
    message = str(error).strip() or error.__class__.__name__
    with _OUTCOME_LOCK:
        _LAST_ERROR = message[:300]
        _LAST_ERROR_AT = time.time()


def reset_llm_outcome() -> None:
    """Forget recorded outcomes; used by tests."""
    global _LAST_ERROR, _LAST_ERROR_AT, _LAST_SUCCESS_AT
    with _OUTCOME_LOCK:
        _LAST_ERROR = _LAST_ERROR_AT = _LAST_SUCCESS_AT = None


def _outcome() -> tuple[str | None, float | None, float | None]:
    with _OUTCOME_LOCK:
        return _LAST_ERROR, _LAST_ERROR_AT, _LAST_SUCCESS_AT


@dataclass(frozen=True)
class LLMInfo:
    """What the running process actually resolved for the LLM."""

    provider: str
    model: str
    available: bool

    @property
    def mode(self) -> str:
        """What the orchestrator will really do on the next question."""
        if not self.available:
            return "deterministic"
        last_error, _, last_success = _outcome()
        if last_error and last_success is None:
            # Configured, tried, and has never once succeeded.
            return "failing"
        return "llm"

    @property
    def healthy(self) -> bool:
        return self.mode != "failing"

    def as_dict(self) -> dict[str, object]:
        last_error, last_error_at, last_success = _outcome()
        return {
            "provider": self.provider,
            "model": self.model or None,
            "available": self.available,
            "mode": self.mode,
            "last_error": last_error,
            "last_error_at": _iso(last_error_at),
            "last_success_at": _iso(last_success),
        }


def _iso(timestamp: float | None) -> str | None:
    if timestamp is None:
        return None
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(timestamp))


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
    if provider == "groq":
        from langchain_groq import ChatGroq

        return ChatGroq(
            api_key=settings.groq_api_key,
            max_tokens=settings.llm_max_tokens,
            **common,
        )
    if provider == "openai_compatible":
        # Hugging Face, OpenRouter, Cerebras, Together, or any gateway that
        # speaks the OpenAI chat-completions API.
        from langchain_openai import ChatOpenAI

        if not settings.llm_model:
            raise ValueError(
                "LLM_MODEL is required with LLM_PROVIDER=openai_compatible; the "
                "model id belongs to whichever endpoint LLM_BASE_URL points at."
            )
        return ChatOpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
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
    except ImportError as exc:
        # The provider package is missing. Record it, because the service
        # otherwise reports a healthy LLM while every question falls back.
        record_llm_failure(
            f"provider package for '{info.provider}' is not installed: {exc}"
        )
        logger.error(
            "LLM provider %s is configured but its package is not installed. "
            "Install it (see requirements-optional.txt) or the orchestrator will "
            "only ever use deterministic routing.",
            info.provider,
        )
        return None
    except Exception as exc:
        record_llm_failure(exc)
        logger.exception("Failed to initialise LLM provider %s (%s)", info.provider, info.model)
        return None
    logger.info("LLM ready: provider=%s model=%s", info.provider, info.model)
    return model


def reset_chat_model_cache() -> None:
    """Drop the cached model; used by tests and after a settings change."""
    get_chat_model.cache_clear()
