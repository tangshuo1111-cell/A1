"""Round 9 — field owner registry and response builder SSOT."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_field_owners_registry_exists() -> None:
    from application.chat.field_owners import CANONICAL_TOP_LEVEL_KEYS, TOP_LEVEL_FIELD_OWNERS

    assert "task_status" in TOP_LEVEL_FIELD_OWNERS
    assert "workflow_elapsed_ms" in TOP_LEVEL_FIELD_OWNERS
    assert "task_status" in CANONICAL_TOP_LEVEL_KEYS


def test_turn_response_builder_apply_functions() -> None:
    text = (PROJECT_ROOT / "backend" / "application" / "chat" / "turn_response_builder.py").read_text(
        encoding="utf-8"
    )
    for fn in (
        "apply_decision_fields",
        "apply_answer_fields",
        "apply_task_fields",
        "apply_material_fields",
        "apply_exit_envelope",
        "build_exit_extra_from_envelope",
    ):
        assert f"def {fn}" in text


def test_merge_compat_fields_lives_in_turn_response_builder() -> None:
    from application.chat.turn_response_builder import merge_compat_fields

    canonical = {"mode": "fast", "pending_kind": "material_pending"}
    source = {"mode": "complex", "v6_takeover": True, "pending_kind": "none"}
    merged = merge_compat_fields(canonical, source)
    assert merged["mode"] == "fast"
    assert merged["pending_kind"] == "material_pending"
    assert merged["v6_takeover"] is True


def test_turn_exit_gate_delegates_to_builder() -> None:
    text = (PROJECT_ROOT / "backend" / "application" / "chat" / "turn_exit_gate.py").read_text(encoding="utf-8")
    assert "apply_exit_envelope" in text
    assert 'out["task_status"]' not in text
    assert 'out["primary_path"]' not in text


def test_entry_paths_use_build_chat_turn_result() -> None:
    canonical_paths = (
        "executors/fast_delivery.py",
        "approval_gate_flow.py",
        "executors/async_path/build_pending.py",
    )
    for rel in canonical_paths:
        text = (PROJECT_ROOT / "backend" / "application" / "chat" / rel).read_text(encoding="utf-8")
        assert "build_chat_turn_result" in text
        assert '"workflow_elapsed_ms":' not in text


def test_check_field_owner_writes_script() -> None:
    proc = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / "check_field_owner_writes.py")],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_apply_exit_envelope_sets_canonical_fields() -> None:
    from application.chat.chat_contracts import TurnExitEnvelope
    from application.chat.turn_response_builder import apply_exit_envelope

    envelope = TurnExitEnvelope(
        task_status="succeeded",
        pending_kind=None,
        primary_path="fast_kb",
        mode="fast",
        executor_profile="fast",
        router_lane="kb",
        material_sufficiency="sufficient",
        quality_gate={"pass": True, "need_second_round": False, "need_more_material": False, "reason_codes": []},
        winner_rule="default_success",
    )
    result = apply_exit_envelope(
        {
            "ok": True,
            "answer": "hi",
            "answer_type": "basic_agno",
            "workflow_elapsed_ms": 42,
            "extra": {"v6_takeover": True, "mode": "complex"},
        },
        envelope,
        source_extra={"v6_takeover": True, "mode": "complex"},
    )
    assert result["task_status"] == "succeeded"
    assert result["primary_path"] == "fast_kb"
    assert result["extra"]["mode"] == "fast"
    assert result["extra"]["v6_takeover"] is True
