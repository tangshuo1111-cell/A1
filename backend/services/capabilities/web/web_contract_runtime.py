"""Runtime helpers for web CapabilityFact contract (S6)."""
from __future__ import annotations

from typing import Any

from services.capabilities.contracts import CapabilityAdvice, CapabilityFact


def attach_web_capability_contract_metadata(
    metadata: dict[str, Any],
    fact: CapabilityFact,
    advice: CapabilityAdvice,
) -> dict[str, Any]:
    merged = dict(metadata or {})
    merged["capability_suggested_mode"] = advice.suggested_mode
    merged["capability_reason"] = advice.reason
    merged["capability_next_action_hint"] = advice.next_action_hint
    merged["capability_probe_elapsed_ms"] = fact.probe_elapsed_ms
    merged["capability_dynamic_required"] = fact.dynamic_required
    merged["capability_cookie_required"] = fact.cookie_required
    merged["capability_quality_level"] = fact.quality_level
    return merged


def is_web_async_recommended(fact: CapabilityFact, advice: CapabilityAdvice) -> bool:
    del fact
    return advice.suggested_mode == "demote_to_async"
