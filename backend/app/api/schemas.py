"""Request and response models for the public API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class WardGeometry(BaseModel):
    type: str
    coordinates: list


class WardResponse(BaseModel):
    ward_id: str
    ward_name: str
    aqi: int
    band: str
    band_color: str
    days_in_band: int
    dominant_source: str
    latitude: float
    longitude: float
    geometry: dict


class ForecastRequest(BaseModel):
    history: list[dict[str, Any]] = Field(
        ..., min_length=1, description="Ward-hour feature rows, oldest first."
    )
    steps: int | None = Field(default=None, ge=1, le=168, description="Horizon in hours.")


class ForecastPoint(BaseModel):
    horizon_hours: int
    prediction: float
    lower: float
    upper: float


class ForecastResponse(BaseModel):
    ward_id: str
    forecast: list[ForecastPoint]
    source: Literal["request_history", "baseline_history"]
    generated_at: str


class AttributionResponse(BaseModel):
    ward_id: str
    timestamp: str
    breakdown: dict[str, float]
    confidence_score: float = Field(ge=0.0, le=1.0)
    method: str


class PriorityItem(BaseModel):
    ward_id: str
    ward_name: str
    aqi: int
    aqi_band: str
    score: float
    dominant_source: str
    source_density_nearby: float
    source_coordinates: list[dict]
    recommendation: str


class PriorityQueueResponse(BaseModel):
    items: list[PriorityItem]
    generated_at: str
    method: str
    disclaimer: str


class AdvisoryResponse(BaseModel):
    ward_id: str
    ward_name: str
    language: str
    aqi: float
    aqi_band: str
    vulnerability_index: float
    advisory: str
    advisory_source: Literal["llm", "template"]
    vulnerability_flags: dict[str, bool]
    delivery_channels: list[str]
    generated_at: str
    disclaimer: str


class OrchestratorRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=1000)
    ward_id: str | None = Field(default=None, max_length=64)
    language: str = Field(default="en", max_length=5)


class ToolCallTrace(BaseModel):
    tool: str | None = None
    agent: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    ok: bool | None = None
    result_preview: str | None = None


class OrchestratorResponse(BaseModel):
    answer: str
    trace: list[ToolCallTrace]
    engine: Literal["langgraph", "deterministic"]
    llm: dict[str, Any]
    ward_id: str | None = None
    cached: bool = False
    elapsed_ms: int


class ToolDescriptor(BaseModel):
    name: str
    agent: str
    description: str
    parameters: dict[str, Any]


class ToolCatalogueResponse(BaseModel):
    orchestrator: str
    engine: Literal["langgraph", "deterministic"]
    llm: dict[str, Any]
    tools: list[ToolDescriptor]


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    environment: str
    models: dict[str, Any]
    orchestrator: dict[str, Any]
