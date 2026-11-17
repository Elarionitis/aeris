"""Aeris agents driven by Google's Agent Development Kit instead of LangGraph.

A small experiment: the same three analytical agents that the LangGraph
orchestrator calls are exposed here as ADK function tools. They reach the
deployed Aeris REST API over HTTP, so this script stays light and proves the
agents are framework-independent -- the orchestration layer is swappable, the
agents are not tied to it.

Run:
    python aeris_adk_agent.py "Why is BTM polluted and will it get worse?"
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv
from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.runners import InMemoryRunner
from google.genai import types

# The Groq key already configured for the main project.
load_dotenv(Path(__file__).resolve().parents[2] / "backend" / ".env")

API_BASE = os.getenv("AERIS_API_BASE", "https://aeris-api-oyuq.onrender.com").rstrip("/")
# LiteLLM routes "groq/<model>" to Groq; the model id is the one the main
# service uses, so both orchestrators reason with the same model.
MODEL = os.getenv("ADK_MODEL", "groq/openai/gpt-oss-120b")
TIMEOUT = httpx.Timeout(90.0, connect=15.0)


def _get(path: str, params: dict | None = None) -> dict:
    """GET a JSON endpoint, returning errors as data.

    An exception raised inside a tool aborts the whole agent run, so every
    failure is handed back to the model as something it can read and react to.
    """
    try:
        response = httpx.get(f"{API_BASE}{path}", params=params, timeout=TIMEOUT)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as exc:
        return {"error": f"API returned {exc.response.status_code} for {path}"}
    except Exception as exc:
        return {"error": f"Could not reach the Aeris API: {exc}"}


# --------------------------------------------------------------------------
# Tools. ADK builds each schema from the signature and docstring, so the
# wording here is the interface the model actually sees.
# --------------------------------------------------------------------------


def list_wards() -> dict:
    """Lists every monitored ward with its current AQI and CPCB band.

    Call this first when the user names a place you are unsure about, or when
    they ask a city-wide question and you need the full ward roster.

    Returns:
        A dict with the ward count, the city average AQI, and a list of wards
        sorted worst first.
    """
    wards = _get("/wards")
    if isinstance(wards, dict) and "error" in wards:
        return wards

    rows = sorted(
        (
            {
                "ward_id": w["ward_id"],
                "ward_name": w["ward_name"],
                "aqi": w["aqi"],
                "band": w["band"],
                "dominant_source": w["dominant_source"],
            }
            for w in wards
        ),
        key=lambda w: w["aqi"],
        reverse=True,
    )
    average = round(sum(w["aqi"] for w in rows) / max(len(rows), 1), 1)
    return {"city": "Bengaluru", "ward_count": len(rows), "city_average_aqi": average, "wards": rows}


def forecast_ward_aqi(ward: str, hours: int) -> dict:
    """Forecasts a ward's AQI up to 72 hours ahead.

    Use this for any question about what the air will be like later today,
    tonight, tomorrow, or over the next few days.

    Args:
        ward: Ward identifier, for example 'BTM' or 'HSR'.
        hours: Forecast horizon in hours, between 1 and 72.

    Returns:
        A dict with the current AQI, the mean forecast, the peak and when it
        arrives, and whether the ward is improving, worsening or stable.
    """
    horizon = max(1, min(int(hours or 24), 72))
    payload = _get(f"/forecast/{ward}", {"hours": horizon})
    if "error" in payload:
        return payload

    points = payload.get("forecast", [])
    if not points:
        return {"error": f"No forecast returned for ward '{ward}'."}

    current = points[0]["prediction"]
    mean = sum(p["prediction"] for p in points) / len(points)
    peak = max(points, key=lambda p: p["prediction"])
    if mean > current + 2:
        direction = "worsening"
    elif mean < current - 2:
        direction = "improving"
    else:
        direction = "stable"

    return {
        "agent": "forecasting",
        "ward_id": payload["ward_id"],
        "horizon_hours": horizon,
        "mean_forecast_aqi": round(mean, 1),
        "peak_aqi": round(peak["prediction"], 1),
        "peak_in_hours": peak["horizon_hours"],
        "direction": direction,
    }


def attribute_ward_sources(ward: str) -> dict:
    """Breaks a ward's pollution into traffic, construction, industrial and other shares.

    Use this for 'why' questions: what is causing the pollution here, which
    source dominates, what should be targeted.

    Args:
        ward: Ward identifier, for example 'BTM' or 'HSR'.

    Returns:
        A dict with percentage shares that sum to 100, the dominant source,
        and the model's confidence score.
    """
    payload = _get(f"/attribution/{ward}")
    if "error" in payload:
        return payload

    breakdown = payload.get("breakdown", {})
    if not breakdown:
        return {"error": f"No attribution returned for ward '{ward}'."}

    dominant = max(breakdown.items(), key=lambda item: item[1])
    return {
        "agent": "attribution",
        "ward_id": payload["ward_id"],
        "breakdown_pct": breakdown,
        "dominant_source": dominant[0],
        "dominant_source_pct": dominant[1],
        "confidence_score": payload.get("confidence_score"),
        "caveat": "Shares are modelled from source-activity proxies, not stack-level measurement.",
    }


def rank_enforcement_priority(limit: int) -> dict:
    """Ranks wards by inspection priority for enforcement teams.

    Use this for 'where should we act first' questions.

    Args:
        limit: How many wards to return, between 1 and 10.

    Returns:
        A dict with the ranked wards, each carrying its score, dominant source
        and a recommendation.
    """
    payload = _get("/enforcement/priority-queue", {"limit": max(1, min(int(limit or 5), 10))})
    if "error" in payload:
        return payload

    return {
        "agent": "enforcement",
        "items": [
            {
                "rank": index + 1,
                "ward_name": item["ward_name"],
                "aqi": item["aqi"],
                "band": item["aqi_band"],
                "score": item["score"],
                "dominant_source": item["dominant_source"],
                "recommendation": item["recommendation"],
            }
            for index, item in enumerate(payload.get("items", []))
        ],
        "disclaimer": payload.get("disclaimer"),
    }


INSTRUCTION = """You are Aeris, an assistant for a city air-quality platform covering Bengaluru.

You coordinate three specialist agents, available to you as tools:
- forecast_ward_aqi: what the air will be like in the next 1-72 hours.
- attribute_ward_sources: which sources are causing a ward's pollution.
- rank_enforcement_priority: where inspection teams should go first.
list_wards is a registry lookup for finding valid wards and current readings.

Ground every number in tool output and never invent one. Call several tools
when a question needs them. If a tool returns an error, say plainly what could
not be computed. Lead with the direct answer, then the supporting numbers.
Keep it under 150 words, plain text.
"""

def _build_model() -> LiteLlm:
    """Build the LiteLLM-backed model, working around Groq reasoning models.

    Groq's gpt-oss models return a reasoning_content field. LiteLLM echoes it
    back on the next turn, and Groq then rejects its own output with
    "property 'reasoning_content' is unsupported", so the run dies on the
    second step -- right after the first tool call succeeds. Asking Groq to
    hide the reasoning means there is nothing to echo.
    """
    extra: dict = {}
    if MODEL.startswith("groq/") and "gpt-oss" in MODEL:
        extra["reasoning_format"] = "hidden"
    return LiteLlm(model=MODEL, **extra)


root_agent = LlmAgent(
    name="aeris_orchestrator",
    model=_build_model(),
    description="Answers air-quality questions by calling the Aeris forecasting, attribution and enforcement agents.",
    instruction=INSTRUCTION,
    tools=[list_wards, forecast_ward_aqi, attribute_ward_sources, rank_enforcement_priority],
)


async def ask(question: str) -> None:
    runner = InMemoryRunner(agent=root_agent, app_name="aeris-adk")
    session = await runner.session_service.create_session(app_name="aeris-adk", user_id="local")

    print(f"API   : {API_BASE}")
    print(f"Model : {MODEL}")
    print(f"Q     : {question}\n")

    called: list[str] = []
    answer = ""

    async for event in runner.run_async(
        user_id="local",
        session_id=session.id,
        new_message=types.Content(role="user", parts=[types.Part(text=question)]),
    ):
        for part in (event.content.parts if event.content else []) or []:
            if getattr(part, "function_call", None):
                called.append(part.function_call.name)
                print(f"  -> calling {part.function_call.name}({dict(part.function_call.args)})")
            elif getattr(part, "text", None) and event.is_final_response():
                answer = part.text

    print(f"\ntools : {called}")
    print(f"A     : {answer.strip()}")


if __name__ == "__main__":
    question = " ".join(sys.argv[1:]) or "Which ward is worst right now and what is driving it?"
    asyncio.run(ask(question))
