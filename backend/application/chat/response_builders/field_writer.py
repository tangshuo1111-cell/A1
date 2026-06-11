"""Focused top-level/result field writers."""

from __future__ import annotations

from typing import Any

from application.chat.chat_contracts import TurnExitEnvelope


def apply_decision_fields(out: dict[str, Any], envelope: TurnExitEnvelope) -> None:
    out["task_status"] = envelope.task_status
    out["primary_path"] = envelope.primary_path


def apply_answer_fields(out: dict[str, Any], *, answer_type: str | None = None) -> None:
    if answer_type is not None and not out.get("answer_type"):
        out["answer_type"] = answer_type


def apply_task_fields(out: dict[str, Any], *, task_id: str | None = None) -> None:
    if task_id is not None and not out.get("task_id"):
        out["task_id"] = task_id


def apply_material_fields(extra: dict[str, Any], envelope: TurnExitEnvelope) -> None:
    if envelope.material_sufficiency is not None:
        extra["material_sufficiency"] = envelope.material_sufficiency
    if envelope.pending_kind is not None:
        extra["pending_kind"] = envelope.pending_kind


def apply_timing_fields(out: dict[str, Any], extra: dict[str, Any]) -> None:
    tms = extra.get("timing_total_ms")
    if tms is None:
        tms = out.get("workflow_elapsed_ms")
    if tms is not None:
        extra["timing_total_ms"] = tms
