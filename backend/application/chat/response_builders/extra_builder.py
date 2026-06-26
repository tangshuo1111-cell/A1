"""Canonical exit extra helper predicates."""

from __future__ import annotations

from typing import Any

from application.chat.chat_contracts import TurnExitEnvelope


def is_complex_task(envelope: TurnExitEnvelope, extra: dict[str, Any]) -> bool:
    from application.chat.complexity_policy import is_complex_task_scope

    return is_complex_task_scope(
        mode=envelope.mode,
        executor_profile=envelope.executor_profile,
        pending_kind=envelope.pending_kind,
        primary_path=envelope.primary_path,
        complex_candidate=bool(extra.get("complex_candidate")),
        complex_reason_codes=tuple(extra.get("complex_reason_codes") or ()),
    )


def insufficient_evidence(envelope: TurnExitEnvelope) -> bool:
    from application.chat.refine_kind import exit_insufficient_evidence

    return exit_insufficient_evidence(envelope)


def has_external_capability_error(extra: dict[str, Any]) -> bool:
    for key in ("v16_doc_error_code", "v16_web_error_code", "v16_video_error_code"):
        val = str(extra.get(key) or "").strip()
        if val and val.lower() not in {"ok", "none", "success", ""}:
            return True
    return False


def resolve_failure_reason_code(envelope: TurnExitEnvelope, extra: dict[str, Any]) -> str:
    status = str(envelope.task_status or "").lower()
    insuf = insufficient_evidence(envelope)
    is_done = status in {"done", "succeeded"}
    if is_done and not insuf and envelope.quality_gate.get("pass", True):
        return "success"
    if insuf:
        return "insufficiency"
    if envelope.winner_rule == "quality_gate_block":
        return "quality_gate_block"
    if envelope.winner_rule == "deadline_pending" or extra.get("hard_deadline_limited"):
        return "timeout_partial"
    if has_external_capability_error(extra):
        return "external_capability_fail"
    if is_complex_task(envelope, extra) and status == "partial":
        return "upgrade_still_partial"
    if status == "partial":
        return "partial_other"
    if status == "failed":
        return "failed_other"
    if is_done and (not envelope.quality_gate.get("pass", True)):
        return "quality_gate_block"
    return "other"

