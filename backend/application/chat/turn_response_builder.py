"""Single writer for ChatTurnResult top-level HTTP fields (see field_owners.py)."""

from __future__ import annotations

from typing import Any

from application.chat.chat_contracts import TurnExitEnvelope
from application.chat.response_builders.base_builder import build_chat_turn_result  # noqa: F401
from application.chat.response_builders.compat_builder import merge_compat_fields  # noqa: F401
from application.chat.response_builders.exit_extra_builder import (
    apply_exit_envelope as _apply_exit_envelope, build_exit_extra_from_envelope as _build_exit_extra_from_envelope,
)
from application.chat.response_builders.field_writer import (
    apply_answer_fields as _apply_answer_fields, apply_decision_fields as _apply_decision_fields,
    apply_material_fields as _apply_material_fields, apply_pipeline_fields as _apply_pipeline_fields,
    apply_task_fields as _apply_task_fields, apply_timing_fields as _apply_timing_fields,
)


def merge_agent_extra_into_turn_extra(
    turn_extra: dict[str, Any],
    agent_extra: dict[str, Any],
) -> dict[str, Any]:
    """Merge validated agent diagnostics; turn-level fields stay with this builder / exit gate."""
    from application.chat.chat_contracts import assert_agent_extra_safe

    merged = dict(turn_extra)
    merged.update(assert_agent_extra_safe(dict(agent_extra)))
    return merged


def apply_decision_fields(out: dict[str, Any], envelope: TurnExitEnvelope) -> None:
    _apply_decision_fields(out, envelope)


def apply_answer_fields(out: dict[str, Any], *, answer_type: str | None = None) -> None:
    _apply_answer_fields(out, answer_type=answer_type)


def apply_task_fields(out: dict[str, Any], *, task_id: str | None | object = None) -> None:
    _apply_task_fields(out, task_id=task_id)


def apply_pipeline_fields(out: dict[str, Any], *, pipeline_ok: bool | None = None) -> None:
    _apply_pipeline_fields(out, pipeline_ok=pipeline_ok)


def apply_material_fields(extra: dict[str, Any], envelope: TurnExitEnvelope) -> None:
    _apply_material_fields(extra, envelope)


def apply_timing_fields(out: dict[str, Any], extra: dict[str, Any]) -> None:
    _apply_timing_fields(out, extra)

def build_exit_extra_from_envelope(
    envelope: TurnExitEnvelope,
    *,
    source_extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return _build_exit_extra_from_envelope(envelope, source_extra=source_extra)


def apply_exit_envelope(
    result: dict[str, Any],
    envelope: TurnExitEnvelope,
    *,
    source_extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return _apply_exit_envelope(result, envelope, source_extra=source_extra)
