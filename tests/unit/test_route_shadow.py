"""Unit tests for route shadow observability fields."""

from __future__ import annotations

from application.ingress.lane_decision_schema import LaneDecision
from application.ingress.request_classifier import classify_request
from application.ingress.route_shadow import attach_route_shadow, route_shadow_extra


def test_attach_route_shadow_populates_fragile_fields(monkeypatch) -> None:
    monkeypatch.setitem(
        __import__("config.feature_flags", fromlist=["FEATURE_FLAGS"]).FEATURE_FLAGS,
        "ENABLE_ROUTE_SHADOW_OBSERVABILITY",
        True,
    )
    decision = LaneDecision(
        lane="general",
        mode="fast",
        router_source="rule",
        router_confidence=0.9,
        router_decision_ms=1,
    )
    signals = classify_request(
        message="compare A and B",
        use_knowledge=False,
        v13_file_content=None,
        v13_text_content=None,
    )
    shadowed = attach_route_shadow(
        decision,
        rule_lane="general",
        rule_mode="fast",
        message="对比 A 和 B 的差异",
        signals=signals,
    )
    extra = route_shadow_extra(shadowed)
    assert extra["route_shadow_rule_lane"] == "general"
    assert "route_shadow_semantic_mode" in extra
    assert isinstance(extra["route_shadow_mode_match"], bool)
