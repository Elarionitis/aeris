"""Tests for the LangGraph orchestrator and its deterministic fallback.

The graph is exercised with a scripted fake chat model, so the tool-calling
loop, the trace builder, and the fallback behaviour are all covered without
an API key or a network call.
"""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage

from app.agents import orchestrator as orchestrator_module
from app.agents.llm import LLMInfo
from app.agents.orchestrator import deterministic_answer, run_orchestrator
from app.agents.tools import AGENT_FUNCTIONS
from app.models.bootstrap import ensure_models


@pytest.fixture(scope="module", autouse=True)
def models_ready():
    assert ensure_models().ready


class ScriptedModel:
    """Chat model that replays a fixed list of replies, newest call first."""

    def __init__(self, replies: list[AIMessage]) -> None:
        self._replies = list(replies)
        self.invocations: list[list] = []

    def bind_tools(self, _tools):
        return self

    def invoke(self, messages):
        self.invocations.append(list(messages))
        return self._replies.pop(0) if self._replies else AIMessage(content="done")


class ExplodingModel:
    def bind_tools(self, _tools):
        return self

    def invoke(self, _messages):
        raise RuntimeError("provider is down")


def use_model(monkeypatch, model) -> None:
    """Point the orchestrator at ``model`` and mark an LLM as available."""
    monkeypatch.setattr(orchestrator_module, "get_chat_model", lambda: model)
    monkeypatch.setattr(
        orchestrator_module,
        "llm_info",
        lambda settings=None: LLMInfo(provider="scripted", model="scripted-1", available=True),
    )
    orchestrator_module.reset_graph_cache()


# --------------------------------------------------------------------------
# Deterministic router
# --------------------------------------------------------------------------


def test_deterministic_why_question_calls_attribution():
    answer, trace = deterministic_answer("Why is BTM so polluted?")
    assert "attribute_ward_sources" in {entry["tool"] for entry in trace}
    assert "BTM" in answer


def test_deterministic_forecast_question_calls_forecasting():
    answer, trace = deterministic_answer("Will HSR Layout get worse tomorrow?")
    assert "forecast_ward_aqi" in {entry["tool"] for entry in trace}
    assert answer


def test_deterministic_enforcement_question_calls_enforcement():
    _, trace = deterministic_answer("Where should inspection teams go first?")
    assert "rank_enforcement_priority" in {entry["tool"] for entry in trace}


def test_deterministic_combines_two_agents():
    _, trace = deterministic_answer("Why is BTM bad and will it get worse tonight?")
    assert {"attribute_ward_sources", "forecast_ward_aqi"} <= {entry["tool"] for entry in trace}


def test_deterministic_uses_dashboard_ward_when_question_has_none():
    _, trace = deterministic_answer("what is going on here", ward_id="Jayanagar")
    assert any(entry["arguments"].get("ward") == "Jayanagar" for entry in trace)


def test_deterministic_trace_records_every_tool_call():
    _, trace = deterministic_answer("Give me a city overview")
    assert trace
    for entry in trace:
        assert entry["tool"] in AGENT_FUNCTIONS
        assert entry["agent"]
        assert entry["ok"] is True


# --------------------------------------------------------------------------
# LangGraph path
# --------------------------------------------------------------------------


def test_graph_runs_tool_loop_and_builds_trace(monkeypatch):
    model = ScriptedModel(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "attribute_ward_sources", "args": {"ward": "BTM"}, "id": "call_1"},
                    {"name": "forecast_ward_aqi", "args": {"ward": "BTM", "hours": 24}, "id": "call_2"},
                ],
            ),
            AIMessage(content="BTM is industrial-dominated and holding steady."),
        ]
    )
    use_model(monkeypatch, model)

    result = run_orchestrator("Why is BTM polluted?", ward_id="BTM")

    assert result["engine"] == "langgraph"
    assert result["answer"] == "BTM is industrial-dominated and holding steady."
    assert [entry["tool"] for entry in result["trace"]] == [
        "attribute_ward_sources",
        "forecast_ward_aqi",
    ]
    assert all(entry["ok"] for entry in result["trace"])
    assert [entry["agent"] for entry in result["trace"]] == ["attribution", "forecasting"]
    orchestrator_module.reset_graph_cache()


def test_graph_records_failed_tool_call(monkeypatch):
    model = ScriptedModel(
        [
            AIMessage(
                content="",
                tool_calls=[{"name": "forecast_ward_aqi", "args": {"ward": "Atlantis"}, "id": "c1"}],
            ),
            AIMessage(content="That ward is not monitored."),
        ]
    )
    use_model(monkeypatch, model)

    result = run_orchestrator("What about Atlantis?")

    assert result["engine"] == "langgraph"
    assert result["trace"][0]["ok"] is False
    orchestrator_module.reset_graph_cache()


def test_graph_sends_system_prompt_and_ward_context(monkeypatch):
    model = ScriptedModel([AIMessage(content="Noted.")])
    use_model(monkeypatch, model)

    run_orchestrator("How is the air?", ward_id="HSR", language="kn")

    first_call = model.invocations[0]
    assert "Aeris" in first_call[0].content
    assert "HSR" in first_call[1].content
    assert "kn" in first_call[1].content
    orchestrator_module.reset_graph_cache()


def test_provider_failure_falls_back_to_deterministic(monkeypatch):
    use_model(monkeypatch, ExplodingModel())

    result = run_orchestrator("Where should enforcement teams go first?")

    assert result["engine"] == "deterministic"
    assert result["answer"]
    assert result["trace"]
    orchestrator_module.reset_graph_cache()


def test_empty_answer_falls_back_to_deterministic(monkeypatch):
    use_model(monkeypatch, ScriptedModel([AIMessage(content="   ")]))

    result = run_orchestrator("Why is BTM polluted?")

    assert result["engine"] == "deterministic"
    orchestrator_module.reset_graph_cache()


# --------------------------------------------------------------------------
# Entry point behaviour
# --------------------------------------------------------------------------


def test_blank_question_is_rejected():
    with pytest.raises(ValueError):
        run_orchestrator("   ")


def test_ward_id_is_canonicalised():
    result = run_orchestrator("Why is it polluted?", ward_id="hsr layout")
    assert result["ward_id"] == "HSR"


def test_response_reports_engine_and_timing():
    result = run_orchestrator("Give me a city overview")
    assert result["engine"] in {"langgraph", "deterministic"}
    assert result["elapsed_ms"] >= 0
    assert result["llm"]["mode"] in {"llm", "deterministic"}
