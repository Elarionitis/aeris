"""LangGraph orchestrator over the three analytical agents.

The graph is the standard tool-calling loop:

    START -> plan -> (tool calls?) -> act -> plan -> ... -> END

``plan`` is an LLM with the three agent tools bound to it. ``act`` executes
whichever tools the model asked for and feeds the results back. The loop runs
until the model answers without requesting another tool, bounded by
``ORCHESTRATOR_MAX_STEPS``.

When no LLM provider is configured the graph is bypassed in favour of
``deterministic_answer``, a keyword router over the same tools. The API shape
is identical either way, so the dashboard works with or without an API key.
"""

from __future__ import annotations

import re
import time
from functools import lru_cache
from typing import Annotated, Any, Sequence, TypedDict

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from app.agents.llm import get_chat_model, llm_info, message_text
from app.agents.tools import AGENT_FUNCTIONS, TOOL_AGENTS, build_tools
from app.core.config import get_settings
from app.core.logging import get_logger
from app.domain.wards import list_ward_ids, resolve_ward_id

logger = get_logger(__name__)

SYSTEM_PROMPT = """You are Aeris, the orchestrator for a city air-quality intelligence platform covering Bengaluru.

You coordinate three specialist agents, each available to you as a tool:
- forecast_ward_aqi: the forecasting agent, for what the air will be like in the next 1-72 hours.
- attribute_ward_sources: the attribution agent, for which sources are causing a ward's pollution.
- rank_enforcement_priority: the enforcement agent, for where inspection teams should go first.
list_wards is a registry lookup you can use to find valid ward names and current readings.

How to work:
- Always ground numeric claims in tool output. Never invent an AQI value, a forecast, a percentage, or a ranking.
- Call several tools when a question needs them. "Why is BTM bad and will it get worse?" needs both attribution and forecasting.
- If a ward name is unclear or you get an unknown-ward error, call list_wards and use the closest real ward.
- If a tool returns an error, say plainly what could not be computed rather than guessing.

How to answer:
- Lead with the direct answer in one or two sentences, then the supporting numbers.
- Use the CPCB band names the tools return (Good, Satisfactory, Moderate, Poor, Very Poor, Severe).
- Keep it under 180 words, plain text, no markdown headings.
- For health guidance stay conservative and general. Never mention medicines, dosages, or treatment.
- Note the relevant caveat when a tool supplies one.
"""


class OrchestratorState(TypedDict):
    """Graph state: the running transcript."""

    messages: Annotated[Sequence[AnyMessage], add_messages]


def _plan_node(state: OrchestratorState) -> dict[str, Any]:
    """Ask the LLM for the next step, with the agent tools bound."""
    model = get_chat_model()
    if model is None:  # pragma: no cover - guarded before the graph is built
        raise RuntimeError("Orchestrator graph requires a configured LLM provider")
    bound = model.bind_tools(build_tools())
    return {"messages": [bound.invoke(state["messages"])]}


def _should_act(state: OrchestratorState) -> str:
    last = state["messages"][-1]
    return "act" if getattr(last, "tool_calls", None) else END


@lru_cache(maxsize=1)
def get_graph():
    """Compile the orchestration graph once per process."""
    graph = StateGraph(OrchestratorState)
    graph.add_node("plan", _plan_node)
    graph.add_node("act", ToolNode(build_tools()))
    graph.add_edge(START, "plan")
    graph.add_conditional_edges("plan", _should_act, {"act": "act", END: END})
    graph.add_edge("act", "plan")
    compiled = graph.compile()
    logger.info("Orchestrator graph compiled with %d agent tools", len(build_tools()))
    return compiled


def reset_graph_cache() -> None:
    get_graph.cache_clear()


def _framing(question: str, ward_id: str | None, language: str) -> str:
    parts = [question.strip()]
    if ward_id:
        parts.append(f"(The user is currently looking at ward {ward_id} on the dashboard.)")
    if language and language != "en":
        parts.append(f"(Answer in the language with ISO code '{language}'.)")
    return "\n".join(parts)


def _trace_from_messages(messages: Sequence[AnyMessage]) -> list[dict[str, Any]]:
    """Pair each tool call with its result, in execution order."""
    requested: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for message in messages:
        if isinstance(message, AIMessage):
            for call in message.tool_calls or []:
                call_id = str(call.get("id") or f"{call.get('name')}-{len(order)}")
                requested[call_id] = {
                    "tool": call.get("name"),
                    "agent": TOOL_AGENTS.get(str(call.get("name")), "unknown"),
                    "arguments": call.get("args") or {},
                    "ok": None,
                    "result_preview": None,
                }
                order.append(call_id)
        elif isinstance(message, ToolMessage):
            entry = requested.get(str(message.tool_call_id))
            if entry is None:
                continue
            content = message.content if isinstance(message.content, str) else str(message.content)
            entry["ok"] = message.status != "error" and '"error"' not in content[:200]
            entry["result_preview"] = content[:400]
    return [requested[call_id] for call_id in order]


def _final_text(messages: Sequence[AnyMessage]) -> str:
    for message in reversed(messages):
        if isinstance(message, AIMessage) and not getattr(message, "tool_calls", None):
            text = message_text(message)
            if text:
                return text
    return ""


# --------------------------------------------------------------------------
# Deterministic fallback
# --------------------------------------------------------------------------

_FORECAST_WORDS = re.compile(
    r"\b(forecast|predict|tomorrow|tonight|later|next\s+\d+|hours?|worse|better|improv\w*|trend|outlook|expect)",
    re.IGNORECASE,
)
_ATTRIBUTION_WORDS = re.compile(
    r"\b(why|cause\w*|source\w*|blame|responsible|driving|traffic|construction|industr\w*|contribut\w*|reason)",
    re.IGNORECASE,
)
_ENFORCEMENT_WORDS = re.compile(
    r"\b(enforce\w*|inspect\w*|priorit\w*|where|worst|first|act|crackdown|team|patrol|rank\w*|top)",
    re.IGNORECASE,
)


def _hours(count: int) -> str:
    return "1 hour" if int(count) == 1 else f"{int(count)} hours"


def _mentioned_ward(question: str) -> str | None:
    """Find a ward named anywhere in the question."""
    lowered = question.casefold()
    for ward_id in sorted(list_ward_ids(), key=len, reverse=True):
        canonical = resolve_ward_id(ward_id)
        if canonical is None:
            continue
        if ward_id.casefold() in lowered:
            return canonical
    from app.domain.wards import WARD_STATE

    for _, row in WARD_STATE.iterrows():
        if str(row.ward_name).casefold() in lowered:
            return str(row.ward_id)
    return None


def deterministic_answer(question: str, ward_id: str | None = None) -> tuple[str, list[dict[str, Any]]]:
    """Answer by keyword-routing to the same tools the LLM would call.

    This keeps the orchestrator endpoint useful with no API key configured. It
    is a router, not a reasoner: it picks tools by keyword and states the
    numbers they return.
    """
    target = _mentioned_ward(question) or resolve_ward_id(ward_id or "") or None
    wants_forecast = bool(_FORECAST_WORDS.search(question))
    wants_attribution = bool(_ATTRIBUTION_WORDS.search(question))
    wants_enforcement = bool(_ENFORCEMENT_WORDS.search(question)) and target is None

    if not any((wants_forecast, wants_attribution, wants_enforcement)):
        # No clear intent: give the city picture plus the ward in focus.
        wants_enforcement = target is None
        wants_attribution = target is not None

    trace: list[dict[str, Any]] = []
    sentences: list[str] = []

    def run(name: str, **kwargs: Any) -> dict[str, Any]:
        result = AGENT_FUNCTIONS[name](**kwargs)
        trace.append(
            {
                "tool": name,
                "agent": TOOL_AGENTS[name],
                "arguments": kwargs,
                "ok": "error" not in result,
                "result_preview": str(result)[:400],
            }
        )
        return result

    if target is None:
        # City-wide question: always open with the roster-level picture.
        overview = run("list_wards")
        sentences.append(
            f"Across {overview['ward_count']} monitored wards the city average is AQI "
            f"{overview['city_average_aqi']} ({overview['city_average_band']}), and "
            f"{overview['wards'][0]['ward_name']} is worst at {overview['wards'][0]['aqi']}."
        )

    if target and wants_attribution:
        result = run("attribute_ward_sources", ward=target)
        if "error" not in result:
            breakdown = result["breakdown_pct"]
            sentences.append(
                f"{result['ward_name']} is at AQI {result['current_aqi']} ({result['current_band']}), and the "
                f"attribution agent puts {result['dominant_source_pct']:.0f}% of it on {result['dominant_source']} "
                f"(traffic {breakdown['traffic']:.0f}%, construction {breakdown['construction']:.0f}%, "
                f"industrial {breakdown['industrial']:.0f}%, other {breakdown['other']:.0f}%; "
                f"confidence {result['confidence_score']:.2f})."
            )

    if target and wants_forecast:
        result = run("forecast_ward_aqi", ward=target, hours=72)
        if "error" not in result:
            sentences.append(
                f"The forecasting agent expects {result['ward_name']} to be {result['direction']} over the next "
                f"{result['horizon_hours']} hours, averaging AQI {result['mean_forecast_aqi']} and peaking at "
                f"{result['peak']['aqi']} ({result['peak']['band']}) in about {_hours(result['peak']['in_hours'])}."
            )

    if target and not wants_forecast and not wants_attribution:
        result = run("forecast_ward_aqi", ward=target, hours=24)
        if "error" not in result:
            sentences.append(
                f"{result['ward_name']} is currently AQI {result['current_aqi']} ({result['current_band']}) and "
                f"looks {result['direction']} over the next 24 hours."
            )

    if wants_enforcement:
        result = run("rank_enforcement_priority", limit=3)
        if "error" not in result and result["items"]:
            ranked = ", ".join(
                f"{item['ward_name']} (AQI {item['aqi']}, score {item['score']:.0f}, mostly {item['dominant_source']})"
                for item in result["items"]
            )
            sentences.append(f"The enforcement agent ranks inspection priority as: {ranked}.")

    if not sentences:
        sentences.append(
            "I could not match that to the forecasting, attribution, or enforcement agents. Try asking about a "
            f"ward's outlook, what is causing its pollution, or where to send inspection teams. Known wards: "
            f"{', '.join(list_ward_ids())}."
        )
    else:
        sentences.append("Figures come from the platform's models; validate against municipal data before enforcement action.")

    return " ".join(sentences), trace


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------


def run_orchestrator(
    question: str,
    ward_id: str | None = None,
    language: str = "en",
) -> dict[str, Any]:
    """Answer ``question`` using the agent tools.

    Returns the answer, the tool-call trace, and which engine produced it.
    Never raises for a model or provider failure: the deterministic router is
    used as the backstop so the endpoint stays available.
    """
    settings = get_settings()
    question = (question or "").strip()
    if not question:
        raise ValueError("question must not be empty")

    info = llm_info(settings)
    started = time.perf_counter()
    canonical_ward = resolve_ward_id(ward_id) if ward_id else None

    if info.available and get_chat_model() is not None:
        try:
            state = get_graph().invoke(
                {
                    "messages": [
                        SystemMessage(content=SYSTEM_PROMPT),
                        HumanMessage(content=_framing(question, canonical_ward, language)),
                    ]
                },
                config={"recursion_limit": settings.orchestrator_max_steps * 2},
            )
            messages = list(state["messages"])
            answer = _final_text(messages)
            if answer:
                return {
                    "answer": answer,
                    "trace": _trace_from_messages(messages),
                    "engine": "langgraph",
                    "llm": info.as_dict(),
                    "ward_id": canonical_ward,
                    "elapsed_ms": int((time.perf_counter() - started) * 1000),
                }
            logger.warning("Orchestrator graph produced no final text; falling back")
        except Exception:
            logger.exception("Orchestrator graph run failed; falling back to deterministic routing")

    answer, trace = deterministic_answer(question, canonical_ward)
    return {
        "answer": answer,
        "trace": trace,
        "engine": "deterministic",
        "llm": info.as_dict(),
        "ward_id": canonical_ward,
        "elapsed_ms": int((time.perf_counter() - started) * 1000),
    }
