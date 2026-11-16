"""Orchestrator endpoints: ask a question, or inspect the agent tools."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

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

logger = get_logger(__name__)

router = APIRouter(prefix="/orchestrator", tags=["orchestrator"])


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
def query_orchestrator(payload: OrchestratorRequest) -> dict[str, object]:
    """Answer a natural-language question by calling the agent tools.

    The LangGraph agent decides which of the forecasting, attribution, and
    enforcement agents to invoke. When no LLM provider is configured, a
    deterministic router over the same tools answers instead; the response
    shape is identical and ``engine`` says which path ran.
    """
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
        },
    )
    return result
