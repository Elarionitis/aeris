"""Tests for the three analytical agents exposed as LLM tools."""

from __future__ import annotations

import pytest

from app.agents.tools import (
    AGENT_FUNCTIONS,
    TOOL_AGENTS,
    attribute_ward_sources,
    build_tools,
    forecast_ward_aqi,
    list_wards,
    rank_enforcement_priority,
    tool_catalogue,
)
from app.models.bootstrap import ensure_models


@pytest.fixture(scope="module", autouse=True)
def models_ready():
    status = ensure_models()
    assert status.ready, status.errors


def test_every_tool_fronts_a_known_agent():
    assert set(AGENT_FUNCTIONS) == set(TOOL_AGENTS)
    assert {"forecasting", "attribution", "enforcement"} <= set(TOOL_AGENTS.values())


def test_tools_build_with_schemas():
    tools = build_tools()
    assert {tool.name for tool in tools} == set(AGENT_FUNCTIONS)
    for tool in tools:
        assert tool.description, f"{tool.name} has no description for the LLM"
        assert tool.args_schema is not None


def test_tool_catalogue_is_json_serialisable():
    for descriptor in tool_catalogue():
        assert descriptor["name"] in AGENT_FUNCTIONS
        assert descriptor["description"]
        assert isinstance(descriptor["parameters"], dict)


def test_list_wards_reports_city_summary():
    result = list_wards()
    assert result["ward_count"] == len(result["wards"])
    # Sorted worst-first so the model sees the hotspots at the top.
    aqis = [ward["aqi"] for ward in result["wards"]]
    assert aqis == sorted(aqis, reverse=True)
    assert result["city_average_band"]


def test_forecast_tool_returns_bounded_summary():
    result = forecast_ward_aqi("BTM", hours=48)
    assert result["agent"] == "forecasting"
    assert result["horizon_hours"] == 48
    assert result["direction"] in {"worsening", "improving", "stable"}
    assert 1 <= result["peak"]["in_hours"] <= 48
    for point in result["by_horizon"]:
        assert point["lower"] <= point["aqi"] <= point["upper"]


def test_forecast_tool_clamps_horizon():
    assert forecast_ward_aqi("BTM", hours=500)["horizon_hours"] == 72
    assert forecast_ward_aqi("BTM", hours=0)["horizon_hours"] == 24


def test_tools_resolve_ward_names_loosely():
    assert forecast_ward_aqi("hsr layout")["ward_id"] == "HSR"
    assert attribute_ward_sources("Koramangla")["ward_id"] == "Koramangala"


def test_unknown_ward_is_reported_not_raised():
    result = forecast_ward_aqi("Atlantis")
    assert "error" in result
    assert "BTM" in result["known_wards"]


def test_attribution_shares_sum_to_100():
    result = attribute_ward_sources("BTM")
    assert result["agent"] == "attribution"
    assert sum(result["breakdown_pct"].values()) == pytest.approx(100.0, abs=0.05)
    assert result["dominant_source"] in result["breakdown_pct"]
    assert 0.0 <= result["confidence_score"] <= 1.0


def test_enforcement_tool_ranks_and_limits():
    result = rank_enforcement_priority(limit=3)
    assert result["agent"] == "enforcement"
    assert [item["rank"] for item in result["items"]] == [1, 2, 3]
    scores = [item["score"] for item in result["items"]]
    assert scores == sorted(scores, reverse=True)
    assert result["disclaimer"]


def test_enforcement_tool_clamps_limit():
    assert len(rank_enforcement_priority(limit=99)["items"]) <= 10
    assert len(rank_enforcement_priority(limit=0)["items"]) == 5
