"""Single exit gate — maps TurnFacts to TurnExitEnvelope (no routing/tools/retrieval)."""

from __future__ import annotations

import logging
from typing import Any

from application.chat.chat_contracts import (
    TurnExitEnvelope,
    TurnExitTaskStatus,
    normalize_task_status,
)
from application.chat.complex_pending_mapping import (
    resolve_final_task_status,
    task_status_for_pending_kind,
)
from application.chat.pending_kind import PendingKind
from application.chat.turn_facts import TurnFacts
from config.feature_flags import turn_exit_gate_shadow_active

logger = logging.getLogger(__name__)

EXIT_COMPARE_FIELDS = ("task_status", "pending_kind", "primary_path", "mode")

# Mutual exclusion priority (first matching rule wins).
_RULE_APPROVAL_BLOCKED = "approval_blocked"
_RULE_HARD_FAILURE = "hard_failure"
_RULE_COMMIT = "commit_executed"
_RULE_ASYNC_PENDING = "async_pending"
_RULE_PENDING_KIND = "pending_kind"
_RULE_DEADLINE_PENDING = "deadline_pending"
_RULE_QUALITY_BLOCK = "quality_gate_block"
_RULE_DEFAULT_SUCCESS = "default_success"


def _quality_gate_dict(gate: Any | None) -> dict[str, Any]:
    if gate is None:
        return {
            "pass": True,
            "need_second_round": False,
            "need_more_material": False,
            "reason_codes": [],
        }
    return {
        "pass": bool(getattr(gate, "pass_", False)),
        "need_second_round": bool(getattr(gate, "need_second_round", False)),
        "need_more_material": bool(getattr(gate, "need_more_material", False)),
        "reason_codes": list(getattr(gate, "reason_codes", ()) or ()),
    }


def _resolve_primary_path(facts: TurnFacts) -> str:
    if facts.approval is not None and (facts.approval.blocked or facts.approval.commit_executed):
        return "approval_gate"
    if facts.async_pending:
        legacy = (facts.primary_path_candidate or "").strip()
        if legacy:
            return legacy
        return f"{facts.router_lane}_async"
    path = (facts.primary_path_candidate or facts.answer_view_path or "").strip()
    if path:
        return path
    if facts.effective_mode == "fast":
        return f"fast_{facts.router_lane}"
    return "complex_rag_answer"


def finalize_turn_exit(facts: TurnFacts) -> TurnExitEnvelope:
    """Map collected facts to exactly one canonical public exit (mutually exclusive rules)."""
    qg = facts.quality_gate
    qg_dict = _quality_gate_dict(qg)
    pending_value = (
        None if facts.pending_kind == PendingKind.NONE else facts.pending_kind.value
    )
    material = facts.material_sufficiency

    winner = _RULE_DEFAULT_SUCCESS
    status: TurnExitTaskStatus = "succeeded"

    if facts.approval is not None and facts.approval.blocked:
        winner = _RULE_APPROVAL_BLOCKED
        status = "blocked"
    elif facts.hard_failure:
        winner = _RULE_HARD_FAILURE
        status = "failed"
    elif facts.approval is not None and facts.approval.commit_executed:
        winner = _RULE_COMMIT
        status = "succeeded" if facts.approval.commit_success else "failed"
    elif facts.async_pending:
        winner = _RULE_ASYNC_PENDING
        status = "pending"
    elif facts.pending_kind != PendingKind.NONE:
        winner = _RULE_PENDING_KIND
        status = task_status_for_pending_kind(facts.pending_kind)  # type: ignore[assignment]
    elif facts.hard_deadline_limited and facts.bundle_pending_item_present:
        winner = _RULE_DEADLINE_PENDING
        status = "pending"
    elif qg is not None and not qg.pass_ and qg.reason_codes and "answer_empty" in qg.reason_codes:
        winner = _RULE_QUALITY_BLOCK
        status = "failed"
    else:
        resolved = resolve_final_task_status(
            pending_kind=facts.pending_kind,
            hard_deadline_limited=facts.hard_deadline_limited,
            bundle_pending_item_present=facts.bundle_pending_item_present,
        )
        status = resolved  # type: ignore[assignment]
        legacy = normalize_task_status(facts.legacy_task_status)
        if legacy and legacy in {"blocked"} and status == "succeeded":
            status = legacy

    mode = str(facts.public_mode or facts.effective_mode or "fast")
    if facts.approval is not None and facts.approval.commit_executed and not facts.public_mode:
        mode = "fast"

    trace: dict[str, Any] = {"winner_rule": winner}
    if facts.limitations:
        trace["limitations_count"] = len(facts.limitations)

    return TurnExitEnvelope(
        task_status=status,
        pending_kind=pending_value,
        primary_path=_resolve_primary_path(facts),
        mode=mode,
        executor_profile=facts.executor_profile,
        router_lane=facts.router_lane,
        material_sufficiency=material,
        quality_gate=qg_dict,
        winner_rule=winner,
        trace=trace,
    )


def envelope_to_extra_fields(envelope: TurnExitEnvelope) -> dict[str, Any]:
    out: dict[str, Any] = {
        "mode": envelope.mode,
        "executor_profile": envelope.executor_profile,
        "router_lane": envelope.router_lane,
        "primary_path": envelope.primary_path,
        "task_status": envelope.task_status,
        "material_sufficiency": envelope.material_sufficiency,
        "quality_gate": dict(envelope.quality_gate),
        "quality_gate.pass": envelope.quality_gate.get("pass", False),
        "quality_gate.need_second_round": envelope.quality_gate.get("need_second_round", False),
        "quality_gate.need_more_material": envelope.quality_gate.get("need_more_material", False),
        "quality_gate.reason_codes": list(envelope.quality_gate.get("reason_codes") or []),
        "exit": dict(envelope.trace),
    }
    if envelope.pending_kind is not None:
        out["pending_kind"] = envelope.pending_kind
    return out


def _normalize_pending_kind(value: str | None) -> str | None:
    raw = str(value or "").strip().lower()
    if not raw or raw == "none":
        return None
    return raw


def _public_snapshot(result: dict[str, Any]) -> dict[str, str | None]:
    extra = dict(result.get("extra") or {})
    mode = str(extra.get("mode") or "")
    raw_status = str(result.get("task_status") or "")
    return {
        "task_status": normalize_task_status(raw_status) or raw_status,
        "pending_kind": _normalize_pending_kind(str(extra.get("pending_kind") or "")),
        "primary_path": str(result.get("primary_path") or extra.get("primary_path") or ""),
        "mode": mode,
    }


def _envelope_snapshot(envelope: TurnExitEnvelope) -> dict[str, str | None]:
    return {
        "task_status": envelope.task_status,
        "pending_kind": _normalize_pending_kind(envelope.pending_kind),
        "primary_path": envelope.primary_path,
        "mode": envelope.mode,
    }


def compare_exit_shadow(
    *,
    old: dict[str, Any],
    envelope: TurnExitEnvelope,
) -> dict[str, Any]:
    old_snap = _public_snapshot(old)
    new_snap = _envelope_snapshot(envelope)
    diff: dict[str, Any] = {}
    for key in EXIT_COMPARE_FIELDS:
        o = old_snap.get(key)
        n = new_snap.get(key)
        # Pre-gate builders omit canonical task_status; gate is SSOT for that field.
        if key == "task_status" and not str(o or "").strip():
            continue
        if o != n:
            diff[key] = {"old": o, "new": n}
    return {
        "old": old_snap,
        "new": new_snap,
        "diff_fields": diff,
        "match": not diff,
        "winner_rule": envelope.winner_rule,
    }


def apply_turn_exit_to_chat_turn(
    result: dict[str, Any],
    *,
    facts: TurnFacts | None = None,
    ingress: Any | None = None,
    effective_mode: str | None = None,
    hard_deadline_limited: bool = False,
    bundle_pending_item_present: bool = False,
) -> dict[str, Any]:
    """Apply canonical exit fields from TurnFacts / TurnExitEnvelope (always single-write)."""
    from application.chat.turn_facts import turn_facts_from_chat_result

    built = facts or turn_facts_from_chat_result(
        result,
        ingress=ingress,
        effective_mode=effective_mode,
        hard_deadline_limited=hard_deadline_limited,
        bundle_pending_item_present=bundle_pending_item_present,
    )
    envelope = finalize_turn_exit(built)
    extra = dict(result.get("extra") or {})

    if turn_exit_gate_shadow_active():
        old_for_shadow = dict(result)
        if facts is not None:
            extra_snap = dict(old_for_shadow.get("extra") or {})
            if built.legacy_task_status:
                old_for_shadow["task_status"] = built.legacy_task_status
            if built.primary_path_candidate:
                old_for_shadow["primary_path"] = built.primary_path_candidate
                extra_snap["primary_path"] = built.primary_path_candidate
            if built.pending_kind != PendingKind.NONE:
                extra_snap["pending_kind"] = built.pending_kind.value
            if built.public_mode:
                extra_snap["mode"] = built.public_mode
            old_for_shadow["extra"] = extra_snap
        shadow = compare_exit_shadow(old=old_for_shadow, envelope=envelope)
        trace_root = dict(extra.get("trace") or {})
        trace_root["exit_shadow"] = shadow
        extra["trace"] = trace_root
        if not shadow["match"]:
            logger.warning(
                "turn_exit_shadow_diff request_id=%s diff=%s winner=%s",
                extra.get("router_request_id"),
                shadow.get("diff_fields"),
                envelope.winner_rule,
            )

    out = dict(result)
    out["task_status"] = envelope.task_status
    out["primary_path"] = envelope.primary_path
    extra.update(envelope_to_extra_fields(envelope))
    out["extra"] = extra
    return out
