"""Cross-capability contracts (§5.2 / §5.3).

Capability layers return facts + advice; Orchestration owns product decisions."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Lane = Literal["video", "web", "document", "kb", "general"]
SuggestedMode = Literal["sync_ok", "demote_to_async", "needs_user_confirm"]
QualityLevel = Literal["good", "usable", "poor", "empty"]
EvidenceOutcome = Literal["ok", "partial", "timeout", "failed", "pending"]


@dataclass(frozen=True)
class CapabilityFact:
    lane: Lane
    probe_elapsed_ms: int
    duration_sec: float | None = None
    subtitle_available: bool | None = None
    dynamic_required: bool | None = None
    cookie_required: bool | None = None
    page_count: int | None = None
    ocr_required: bool | None = None
    estimated_sync_cost_ms: int = 0
    quality_level: QualityLevel = "usable"
    artifact_ref: str | None = None
    error_code: str = ""
    failure_reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CapabilityAdvice:
    suggested_mode: SuggestedMode
    reason: str
    next_action_hint: str = ""


@dataclass(frozen=True)
class EvidenceEnvelope:
    """Worker → Middle material envelope (§5.3 / 12.md §5.3)."""

    source: str
    lane: Lane
    outcome: EvidenceOutcome
    elapsed_ms: int
    content: str = ""
    error_code: str = ""
    failure_reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
