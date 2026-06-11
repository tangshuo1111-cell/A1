"""Canonical exit extra assembly."""

from __future__ import annotations

from typing import Any

from application.chat.chat_contracts import TurnExitEnvelope
from application.chat.response_builders.compat_builder import merge_compat_fields
from application.chat.response_builders.extra_builder import (
    insufficient_evidence,
    is_complex_task,
    resolve_failure_reason_code,
)
from application.chat.response_builders.field_writer import (
    apply_decision_fields,
    apply_material_fields,
    apply_timing_fields,
)


def build_exit_extra_from_envelope(
    envelope: TurnExitEnvelope,
    *,
    source_extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source_extra = source_extra or {}
    qg_pass = bool(envelope.quality_gate.get("pass", False))
    is_complex = is_complex_task(envelope, source_extra)
    extra: dict[str, Any] = {
        "mode": envelope.mode,
        "executor_profile": envelope.executor_profile,
        "router_lane": envelope.router_lane,
        "primary_path": envelope.primary_path,
        "task_status": envelope.task_status,
        "material_sufficiency": envelope.material_sufficiency,
        "quality_gate": dict(envelope.quality_gate),
        "quality_gate.pass": qg_pass,
        "quality_gate.need_second_round": envelope.quality_gate.get("need_second_round", False),
        "quality_gate.need_more_material": envelope.quality_gate.get("need_more_material", False),
        "quality_gate.reason_codes": list(envelope.quality_gate.get("reason_codes") or []),
        "quality_gate_passed": qg_pass,
        "insufficient_evidence": insufficient_evidence(envelope),
        "is_complex_task": is_complex,
        "exit": dict(envelope.trace),
    }
    if envelope.pending_kind is not None:
        extra["pending_kind"] = envelope.pending_kind
    extra["failure_reason_code"] = resolve_failure_reason_code(envelope, {**source_extra, **extra})
    return extra


def apply_exit_envelope(
    result: dict[str, Any],
    envelope: TurnExitEnvelope,
    *,
    source_extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source_extra = dict(source_extra or result.get("extra") or {})
    out = dict(result)
    extra = dict(source_extra)

    apply_decision_fields(out, envelope)
    canonical_extra = build_exit_extra_from_envelope(envelope, source_extra=source_extra)
    extra = merge_compat_fields(canonical_extra, extra)
    apply_material_fields(extra, envelope)
    apply_timing_fields(out, extra)
    extra["answer_char_count"] = len(str(result.get("answer") or ""))
    out["extra"] = extra
    return out
