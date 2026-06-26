"""Single exit gate — maps TurnFacts to TurnExitEnvelope (no routing/tools/retrieval)."""

from __future__ import annotations

import logging
import re
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
from application.chat.complexity_policy import is_complex_task_scope
from application.chat.pending_kind import PendingKind
from application.chat.turn_facts import TurnFacts
from config.feature_flags import turn_exit_gate_shadow_active

logger = logging.getLogger(__name__)

_MESSAGE_TEXT_MAX = 2000
_ANSWER_SUMMARY_MAX = 1500
_SANDBOX_SESSION_RE = re.compile(r"^sandbox_(.+?)_[0-9a-f]{8}$", re.IGNORECASE)

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
    if facts.answer_only_exit_reconcile:
        trace["answer_only_exit_reconcile"] = True

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


def _is_complex_task(
    envelope: TurnExitEnvelope,
    source_extra: dict[str, Any] | None = None,
) -> bool:
    """Product metrics v1: complex + async scope."""
    source_extra = source_extra or {}
    return is_complex_task_scope(
        mode=envelope.mode,
        executor_profile=envelope.executor_profile,
        pending_kind=envelope.pending_kind,
        primary_path=envelope.primary_path,
        complex_candidate=bool(source_extra.get("complex_candidate")),
        complex_reason_codes=tuple(source_extra.get("complex_reason_codes") or ()),
    )


def _insufficient_evidence(envelope: TurnExitEnvelope) -> bool:
    """Product metrics v1: canonical insufficiency (single exit write)."""
    from application.chat.refine_kind import exit_insufficient_evidence

    return exit_insufficient_evidence(envelope)


def _has_external_capability_error(extra: dict[str, Any]) -> bool:
    for key in (
        "v16_doc_error_code",
        "v16_web_error_code",
        "v16_video_error_code",
    ):
        val = str(extra.get(key) or "").strip()
        if val and val.lower() not in {"ok", "none", "success", ""}:
            return True
    return False


def _resolve_failure_reason_code(
    envelope: TurnExitEnvelope,
    extra: dict[str, Any],
) -> str:
    status = str(envelope.task_status or "").lower()
    insuf = _insufficient_evidence(envelope)
    is_done = status in {"done", "succeeded"}
    if is_done and not insuf and envelope.quality_gate.get("pass", True):
        return "success"
    if insuf:
        return "insufficiency"
    if envelope.winner_rule == _RULE_QUALITY_BLOCK:
        return "quality_gate_block"
    if envelope.winner_rule == _RULE_DEADLINE_PENDING or extra.get("hard_deadline_limited"):
        return "timeout_partial"
    if _has_external_capability_error(extra):
        return "external_capability_fail"
    if _is_complex_task(envelope) and status == "partial":
        return "upgrade_still_partial"
    if status == "partial":
        return "partial_other"
    if status == "failed":
        return "failed_other"
    if is_done and (not envelope.quality_gate.get("pass", True)):
        return "quality_gate_block"
    return "other"


def _answer_summary(text: str, *, limit: int = _ANSWER_SUMMARY_MAX) -> str:
    normalized = " ".join((text or "").split())
    if not normalized:
        return ""
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1] + "…"


def _sample_label_from_session(session_id: str | None) -> str | None:
    if not session_id:
        return None
    match = _SANDBOX_SESSION_RE.match(str(session_id))
    return match.group(1) if match else None


def _normalize_message_text(value: str | None) -> str | None:
    text = " ".join(str(value or "").split())
    if not text:
        return None
    return text[:_MESSAGE_TEXT_MAX]


def _timing_total_ms(extra: dict[str, Any], result: dict[str, Any]) -> int | None:
    for key in ("timing_total_ms", "workflow_elapsed_ms"):
        val = extra.get(key) if key in extra else result.get(key)
        if isinstance(val, (int, float)) and val >= 0:
            return int(val)
    return None


def _record_product_metrics_snapshot(
    out: dict[str, Any],
    envelope: TurnExitEnvelope,
    *,
    user_message: str | None = None,
) -> None:
    extra = dict(out.get("extra") or {})
    if extra.get("_product_metrics_recorded"):
        return
    msg = _normalize_message_text(user_message or extra.get("user_message"))
    if not msg:
        return
    extra["user_message"] = msg
    task_id = str(out.get("task_id") or extra.get("task_id") or out.get("request_id") or "")
    if not task_id:
        task_id = str(extra.get("router_request_id") or "unknown")
    answer = str(out.get("answer") or "")
    try:
        from storage.turn_product_metrics_pg import insert_turn_product_metrics

        insert_turn_product_metrics(
            task_id=task_id,
            session_id=out.get("session_id"),
            request_id=out.get("request_id"),
            task_status=str(out.get("task_status") or envelope.task_status),
            mode=str(envelope.mode or ""),
            executor_profile=str(envelope.executor_profile or extra.get("executor_profile") or ""),
            is_complex_task=_is_complex_task(envelope, extra),
            quality_gate_passed=bool(extra.get("quality_gate_passed")),
            insufficient_evidence=bool(extra.get("insufficient_evidence")),
            timing_total_ms=_timing_total_ms(extra, out),
            answer_char_count=len(answer),
            retrieved_chunks_count=int(extra.get("v15_retrieved_chunks_count") or 0),
            temporary_materials_count=int(extra.get("v15_temporary_materials_count") or 0),
            failure_reason_code=str(extra.get("failure_reason_code") or ""),
            sample_label=_sample_label_from_session(out.get("session_id")),
            message_text=msg,
            answer_summary=_answer_summary(answer),
            user_committed_retrieval_hit=bool(extra.get("user_committed_retrieval_hit")),
        )
        extra["_product_metrics_recorded"] = True
        out["extra"] = extra
    except Exception as exc:  # noqa: BLE001
        logger.warning("product metrics snapshot skipped task_id=%s err=%s", task_id, exc)


def envelope_to_extra_fields(
    envelope: TurnExitEnvelope,
    *,
    source_extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Deprecated alias — use ``turn_response_builder.build_exit_extra_from_envelope``."""
    from application.chat.turn_response_builder import build_exit_extra_from_envelope

    return build_exit_extra_from_envelope(envelope, source_extra=source_extra)


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
    user_message: str | None = None,
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
    source_extra = dict(extra)

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
        source_extra = dict(extra)

    from application.chat.turn_response_builder import apply_exit_envelope

    out = apply_exit_envelope(result, envelope, source_extra=source_extra)
    _record_product_metrics_snapshot(out, envelope, user_message=user_message)
    return out
