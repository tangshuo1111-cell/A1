"""Collaboration trace helpers — fixed schema for extra.collaboration_trace (§5.7)."""
from __future__ import annotations

from typing import Any, Literal

TraceStage = Literal[
    "ingress",
    "main",
    "middle",
    "worker",
    "capability",
    "answer",
    "arbitrator",
    "task",
]
TraceOutcome = Literal["ok", "partial", "timeout", "failed", "pending"]


def trace_record(
    *,
    stage: TraceStage,
    name: str,
    elapsed_ms: int,
    outcome: TraceOutcome = "ok",
    reason: str = "",
    **fields: Any,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "stage": stage,
        "name": name,
        "elapsed_ms": max(0, int(elapsed_ms)),
        "outcome": outcome,
        "reason": reason or "",
    }
    record.update(fields)
    return record


def append_trace(
    records: list[dict[str, Any]] | None,
    record: dict[str, Any],
) -> list[dict[str, Any]]:
    base = list(records or [])
    base.append(record)
    return base


def append_arbitrator_trace(
    records: list[dict[str, Any]] | None,
    *,
    name: str,
    decided_mode: str,
    reason: str,
    elapsed_ms: int,
) -> list[dict[str, Any]]:
    return append_trace(
        records,
        trace_record(
            stage="arbitrator",
            name=name,
            elapsed_ms=elapsed_ms,
            outcome="ok",
            reason=reason,
            decided_mode=decided_mode,
        ),
    )


def apply_arbitrator_extra(
    extra: dict[str, Any],
    *,
    ingress_mode: str,
    decided_mode: str,
    decided_reason: str,
    collaboration_trace: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    extra = dict(extra)
    extra["mode"] = decided_mode
    extra["executor_profile"] = decided_mode
    extra["arbitrator.decided_mode"] = decided_mode
    extra["arbitrator.decided_reason"] = decided_reason
    extra["arbitrator.ingress_mode"] = ingress_mode
    if collaboration_trace:
        existing = list(extra.get("collaboration_trace") or [])
        extra["collaboration_trace"] = [*existing, *collaboration_trace]
    return extra


def apply_quality_gate_extra(
    extra: dict[str, Any],
    *,
    gate: Any,
    complex_candidate: bool,
    fast_gate_pass: bool | None = None,
) -> dict[str, Any]:
    extra = dict(extra)
    extra["complex_candidate"] = complex_candidate
    extra["quality_gate.pass"] = bool(getattr(gate, "pass_", False))
    extra["quality_gate.upgrade_profile"] = bool(getattr(gate, "upgrade_profile", False))
    extra["quality_gate.need_second_round"] = bool(getattr(gate, "need_second_round", False))
    extra["quality_gate.need_more_material"] = bool(getattr(gate, "need_more_material", False))
    extra["quality_gate.reason_codes"] = list(getattr(gate, "reason_codes", ()) or ())
    if fast_gate_pass is not None:
        extra["fast_gate_pass"] = fast_gate_pass
    upgrade_codes = list(getattr(gate, "reason_codes", ()) or ())
    if getattr(gate, "upgrade_profile", False):
        extra["upgrade_to_agent_reason"] = upgrade_codes
    if getattr(gate, "need_second_round", False):
        extra["refine_reason_codes"] = upgrade_codes
    return extra


def apply_profile_exit_extra(
    extra: dict[str, Any],
    *,
    profile_exit_reason: str,
    from_profile: str,
    to_profile: str,
) -> dict[str, Any]:
    extra = dict(extra)
    extra["profile_exit_reason"] = profile_exit_reason
    extra["profile_exit.from"] = from_profile
    extra["profile_exit.to"] = to_profile
    extra["executor_profile"] = to_profile
    extra["mode"] = to_profile
    return extra


def apply_ingress_complex_extra(
    extra: dict[str, Any],
    *,
    complex_candidate: bool,
    complex_triggers: list[str] | None = None,
    complex_reason_codes: list[str] | None = None,
) -> dict[str, Any]:
    extra = dict(extra)
    extra["complex_candidate"] = complex_candidate
    if complex_triggers is not None:
        extra["complex_triggers"] = list(complex_triggers)
    if complex_reason_codes is not None:
        extra["complex_reason_codes"] = list(complex_reason_codes)
    return extra
