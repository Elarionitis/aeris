"""Orchestrator endpoints: ask a question, or inspect the agent tools."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response

from app.agents.llm import llm_info
from app.agents.orchestrator import run_orchestrator
from app.agents.tools import tool_catalogue
from app.api.schemas import (
    OrchestratorRequest,
    OrchestratorResponse,
    ToolCatalogueResponse,
)
from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.ratelimit import FixedWindowLimiter, client_key

logger = get_logger(__name__)

router = APIRouter(prefix="/orchestrator", tags=["orchestrator"])

_LIMITER: FixedWindowLimiter | None = None


def get_limiter() -> FixedWindowLimiter:
    """Process-wide limiter, built on first use from settings."""
    global _LIMITER
    if _LIMITER is None:
        settings = get_settings()
        _LIMITER = FixedWindowLimiter(
            capacity=settings.orchestrator_rate_limit,
            window_seconds=settings.orchestrator_rate_window_seconds,
        )
    return _LIMITER


def reset_limiter() -> None:
    """Drop the limiter; used by tests and after a settings change."""
    global _LIMITER
    _LIMITER = None


@router.get("/tools", response_model=ToolCatalogueResponse)
def list_agent_tools() -> dict[str, object]:
    """Describe the agent tools the orchestrator can call."""
    info = llm_info(get_settings())
    return {
        "orchestrator": "Aeris",
        "engine": "langgraph" if info.available else "deterministic",
        "llm": info.as_dict(),
        "tools": tool_catalogue(),
    }


@router.post("/query", response_model=OrchestratorResponse)
def query_orchestrator(
    payload: OrchestratorRequest,
    request: Request,
    response: Response,
) -> dict[str, object]:
    """Answer a natural-language question by calling the agent tools.

    The LangGraph agent decides which of the forecasting, attribution, and
    enforcement agents to invoke. When no LLM provider is configured, a
    deterministic router over the same tools answers instead; the response
    shape is identical and ``engine`` says which path ran.
    """
    # Every call can spend provider quota, so the ceiling is enforced before
    # any work happens. Cached answers still count: the limit protects the
    # endpoint, not only the provider.
    limiter = get_limiter()
    verdict = limiter.check(client_key(request))
    response.headers["x-ratelimit-limit"] = str(verdict.limit)
    response.headers["x-ratelimit-remaining"] = str(verdict.remaining)
    if not verdict.allowed:
        logger.warning("orchestrator rate limit hit", extra={"retry_after": verdict.retry_after})
        raise HTTPException(
            status_code=429,
            detail=(
                f"Rate limit reached ({verdict.limit} questions per "
                f"{limiter.window_seconds // 60 or 1} minutes). Try again shortly."
            ),
            headers={"Retry-After": str(verdict.retry_after)},
        )

    try:
        result = run_orchestrator(
            question=payload.question,
            ward_id=payload.ward_id,
            language=payload.language,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Orchestrator query failed")
        raise HTTPException(status_code=500, detail="Orchestrator failed to answer") from exc

    logger.info(
        "orchestrator query handled",
        extra={
            "engine": result["engine"],
            "tools": [entry.get("tool") for entry in result["trace"]],
            "elapsed_ms": result["elapsed_ms"],
            "cached": result.get("cached", False),
        },
    )
    return result
