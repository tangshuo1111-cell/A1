"""Pre-gate exit hints for TurnFacts — not canonical public response fields.

TurnExitGate owns ``task_status``, ``primary_path``, and ``extra.pending_kind`` on the
final ChatTurnResult. Assembly and other pre-gate builders must use the keys below."""

from __future__ import annotations

from typing import Any

EXIT_SIGNAL_PENDING_KIND = "exit_signal_pending_kind"
EXIT_SIGNAL_PRIMARY_PATH = "exit_signal_primary_path"
EXIT_SIGNAL_MODE = "exit_signal_mode"
EXIT_SIGNAL_MATERIAL_SUFFICIENCY = "exit_signal_material_sufficiency"


def set_pending_kind_signal(extra: dict[str, Any], value: str) -> None:
    extra[EXIT_SIGNAL_PENDING_KIND] = value


def set_primary_path_signal(extra: dict[str, Any], value: str) -> None:
    extra[EXIT_SIGNAL_PRIMARY_PATH] = value


def set_mode_signal(extra: dict[str, Any], value: str) -> None:
    extra[EXIT_SIGNAL_MODE] = value


def set_material_sufficiency_signal(extra: dict[str, Any], value: str) -> None:
    extra[EXIT_SIGNAL_MATERIAL_SUFFICIENCY] = value


def pending_kind_signal_from_extra(extra: dict[str, Any]) -> str | None:
    raw = str(extra.get(EXIT_SIGNAL_PENDING_KIND) or "").strip()
    return raw or None


def primary_path_signal_from_extra(extra: dict[str, Any]) -> str | None:
    raw = str(extra.get(EXIT_SIGNAL_PRIMARY_PATH) or "").strip()
    return raw or None


def mode_signal_from_extra(extra: dict[str, Any]) -> str | None:
    raw = str(extra.get(EXIT_SIGNAL_MODE) or "").strip()
    return raw or None


def material_sufficiency_signal_from_extra(extra: dict[str, Any]) -> str | None:
    raw = str(extra.get(EXIT_SIGNAL_MATERIAL_SUFFICIENCY) or "").strip()
    return raw or None
