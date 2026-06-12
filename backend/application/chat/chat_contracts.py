"""Turn-level contracts for executor profiles, retrieval snapshots, and quality gates."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

# Canonical public task_status values (HTTP extra + ChatTurnResult top-level).
TurnExitTaskStatus = Literal["pending", "succeeded", "failed", "blocked", "partial"]
CANONICAL_TASK_STATUSES: frozenset[str] = frozenset(
    {"pending", "succeeded", "failed", "blocked", "partial"}
)
# Legacy aliases accepted only when normalizing shadow compare / inbound facts.
_TASK_STATUS_ALIASES: dict[str, TurnExitTaskStatus] = {
    "done": "succeeded",
    "completed": "succeeded",
    "routed": "succeeded",
}

ExecutorProfile = Literal["fast", "complex", "async"]
EvidenceTier = Literal["none", "weak", "usable", "strong"]
KbSufficiencyLevel = Literal["none", "weak", "adequate_simple", "adequate_complex", "insufficient"]
MaterialSufficiencyLevel = Literal["sufficient", "insufficient", "no_match", "low_confidence"]

# unified material lifecycle (prepare → pending_commit → committed)
MaterialState = Literal["prepared", "pending_commit", "committed", "discarded", "failed"]
MaterialSource = Literal["text", "upload", "web", "local_video", "web_video", "document"]

# Trace layer labels (HTTP extra — unchanged across rounds)
MaterialLayer = Literal["temporary", "pending", "committed"]
MaterialScope = Literal["session", "pending", "knowledge"]


@dataclass(frozen=True)
class ComplexCandidateSignal:
    complex_candidate: bool = False
    triggers: tuple[str, ...] = ()
    reason_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class RetrievalSnapshot:
    chunks: tuple[Any, ...] = ()
    hits: int = 0
    top_score: float = 0.0
    evidence_tier: EvidenceTier = "none"
    strategy_requested: str = "auto"
    strategy_used: str = ""
    rag_miss: bool = True
    trace_info: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class KbSufficiencyResult:
    level: KbSufficiencyLevel = "none"
    adequate: bool = False
    reason_codes: tuple[str, ...] = ()
    hits: int = 0
    top_score: float = 0.0
    evidence_tier: EvidenceTier = "none"


@dataclass(frozen=True)
class MaterialSufficiencyResult:
    level: MaterialSufficiencyLevel = "sufficient"
    adequate: bool = True
    reason_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class MaterialGateFacts:
    """Middle 产出的只读材料事实，供 quality_gate 消费（gate 只读、不重判）。"""

    material_sufficiency: str = "sufficient"
    material_still_insufficient: bool = False
    try_rag_executed: bool = False
    has_web_evidence: bool = False
    allow_web: bool = False


@dataclass(frozen=True)
class QualityGateResult:
    pass_: bool = False
    upgrade_profile: bool = False
    need_second_round: bool = False
    need_more_material: bool = False
    reason_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProfileExit:
    profile_exit_reason: str = ""
    from_profile: ExecutorProfile = "fast"
    to_profile: ExecutorProfile = "async"


@dataclass(frozen=True)
class SharedMaterialPrepResult:
    snapshot: RetrievalSnapshot | None = None
    kb_sufficiency: KbSufficiencyResult | None = None
    knowledge_block: str | None = None
    material_text: str | None = None
    capabilities_called: tuple[str, ...] = ()
    trace_extra: dict[str, Any] = field(default_factory=dict)
    supplementary_retrieve: bool = False


def normalize_task_status(value: str | None) -> TurnExitTaskStatus | None:
    """Map legacy/internal status strings to canonical exit status."""
    raw = str(value or "").strip().lower()
    if not raw:
        return None
    if raw in CANONICAL_TASK_STATUSES:
        return raw  # type: ignore[return-value]
    return _TASK_STATUS_ALIASES.get(raw)


@dataclass(frozen=True)
class ApprovalExitSignal:
    blocked: bool = False
    commit_executed: bool = False
    commit_success: bool | None = None


@dataclass(frozen=True)
class TurnExitEnvelope:
    """Single source for user-visible exit fields on /chat/agno."""

    task_status: TurnExitTaskStatus
    pending_kind: str | None
    primary_path: str
    mode: str
    executor_profile: str
    router_lane: str
    material_sufficiency: str | None
    quality_gate: dict[str, Any]
    winner_rule: str
    trace: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Agent stage results — agents must not emit HTTP / routing fields
# ---------------------------------------------------------------------------

AGENT_FORBIDDEN_EXTRA_KEYS: frozenset[str] = frozenset(
    {
        "ok",
        "task_id",
        "workflow_elapsed_ms",
        "http_status",
        "primary_path",
        "route_response_flags",
        "task_status",
    }
)


def coerce_main_agent_result(value: Any) -> MainAgentResult:
    if isinstance(value, MainAgentResult):
        return value
    return MainAgentResult(plan=value)


def coerce_middle_agent_result(value: Any) -> MiddleAgentResult:
    if isinstance(value, MiddleAgentResult):
        return value
    return MiddleAgentResult(bundle=value)


def coerce_answer_agent_result(value: Any) -> AnswerAgentResult:
    if isinstance(value, AnswerAgentResult):
        return value
    if isinstance(value, tuple) and len(value) == 2:
        return AnswerAgentResult(answer_text=value[0], huida_pan=value[1])
    raise TypeError(f"cannot coerce answer agent result from {type(value)!r}")


def assert_agent_extra_safe(extra: dict[str, Any]) -> dict[str, Any]:
    """Reject agent-owned extras that collide with turn-level HTTP fields."""
    bad = AGENT_FORBIDDEN_EXTRA_KEYS.intersection(extra.keys())
    if bad:
        raise ValueError(f"agent extra must not set turn-level fields: {sorted(bad)}")
    return extra


@dataclass(frozen=True)
class PreparedMaterial:
    """Parsed in-turn material — not yet in pending store (prepare 只解析、不入库)."""

    pending_id: str
    session_id: str
    source: MaterialSource
    title: str = ""
    preview_text: str = ""
    state: MaterialState = "prepared"


@dataclass(frozen=True)
class PendingMaterial:
    """Awaiting user commit (pending store, not ingested)."""

    pending_id: str
    session_id: str
    source: MaterialSource
    title: str = ""
    preview_text: str = ""
    state: MaterialState = "pending_commit"
    error_code: str = ""


@dataclass(frozen=True)
class CommittedMaterial:
    """Post-commit — written to knowledge store."""

    pending_id: str
    source_id: str
    session_id: str
    source: MaterialSource
    chunk_count: int = 0
    title: str = ""
    state: MaterialState = "committed"
    success: bool = True
    error_code: str = ""


@dataclass(frozen=True)
class MainAgentResult:
    """Main stage — collaboration plan only; no turn exit fields."""

    plan: Any
    collab_trace: tuple[str, ...] = ()


@dataclass(frozen=True)
class MiddleAgentResult:
    """Middle stage — material bundle + optional gate facts for quality_gate."""

    bundle: Any
    material_gate_facts: MaterialGateFacts | None = None


@dataclass(frozen=True)
class AnswerAgentResult:
    """Answer stage — final text + pan; agent_extra is v6_* diagnostics only."""

    answer_text: str
    huida_pan: Any
    agent_extra: dict[str, Any] = field(default_factory=dict)

    def __iter__(self):
        yield self.answer_text
        yield self.huida_pan
