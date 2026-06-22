from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .main_plan_hints import MainPlanHints

LaneName = Literal["video", "document", "web", "kb", "general"]
ModeName = Literal["fast", "complex", "async"]
RouterSourceName = Literal["rule", "light_classifier", "main_agent"]


class LaneDecision(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    request_id: str = ""
    session_id: str = ""
    lane: LaneName
    mode: ModeName
    router_source: RouterSourceName
    router_confidence: float = Field(..., ge=0.0, le=1.0)
    router_fallback: bool = False
    router_decision_ms: int = Field(..., ge=0)
    escalated_to_main_agent: bool = False
    cached_main_hints: MainPlanHints | None = None
    complex_candidate: bool = False
    complex_triggers: list[str] = Field(default_factory=list)
    complex_reason_codes: list[str] = Field(default_factory=list)
    # C-level route shadow observability (fragile; not hard-fail contract)
    route_shadow_rule_lane: str | None = None
    route_shadow_rule_mode: ModeName | None = None
    route_shadow_semantic_mode: ModeName | None = None
    route_shadow_semantic_confidence: float | None = None
    route_shadow_lane_match: bool | None = None
    route_shadow_mode_match: bool | None = None
    route_shadow_semantic_mode_match: bool | None = None
