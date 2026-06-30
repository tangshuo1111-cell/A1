"""Runtime helpers for video CapabilityFact contract (S4b)."""
from __future__ import annotations

from typing import Any, Literal, cast

from services.capabilities.contracts import CapabilityAdvice, SuggestedMode, CapabilityFact


def attach_capability_contract_metadata(
    metadata: dict[str, Any],
    fact: CapabilityFact,
    advice: CapabilityAdvice,
) -> dict[str, Any]:
    merged = dict(metadata or {})
    merged["capability_suggested_mode"] = advice.suggested_mode
    merged["capability_reason"] = advice.reason
    merged["capability_next_action_hint"] = advice.next_action_hint
    merged["capability_probe_elapsed_ms"] = fact.probe_elapsed_ms
    merged["capability_duration_sec"] = fact.duration_sec
    merged["capability_quality_level"] = fact.quality_level
    if fact.artifact_ref:
        merged["artifact_ref"] = fact.artifact_ref
    return merged


def advice_from_tool_result(result: Any) -> CapabilityAdvice | None:
    meta = dict(getattr(result, "metadata", {}) or {})
    suggested = str(meta.get("capability_suggested_mode") or "").strip()
    if not suggested:
        return None
    return CapabilityAdvice(
        suggested_mode=cast(SuggestedMode, suggested),
        reason=str(meta.get("capability_reason") or ""),
        next_action_hint=str(meta.get("capability_next_action_hint") or ""),
    )


def is_video_background_recommended(result: Any) -> bool:
    advice = advice_from_tool_result(result)
    return advice is not None and advice.suggested_mode == "demote_to_async"


def tool_surface_status(*, legacy_status: str, advice: CapabilityAdvice | None) -> str:
    if advice is not None and advice.suggested_mode == "demote_to_async":
        return "queued"
    return legacy_status
