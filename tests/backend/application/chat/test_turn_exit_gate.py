"""Unit tests for turn_exit_gate — mutual exclusion and canonical exit mapping."""
from __future__ import annotations

from application.chat.chat_contracts import (
    ApprovalExitSignal,
    QualityGateResult,
    normalize_task_status,
)
from application.chat.exit_signals import EXIT_SIGNAL_PENDING_KIND
from application.chat.pending_kind import PendingKind
from application.chat.turn_exit_gate import (
    EXIT_COMPARE_FIELDS,
    compare_exit_shadow,
    finalize_turn_exit,
)
from application.chat.turn_facts import TurnFacts


def test_canonical_task_status_aliases() -> None:
    assert normalize_task_status("completed") == "succeeded"
    assert normalize_task_status("done") == "succeeded"


def test_fast_success() -> None:
    env = finalize_turn_exit(
        TurnFacts(
            router_lane="general",
            effective_mode="fast",
            executor_profile="fast",
            primary_path_candidate="direct_llm",
            legacy_task_status="succeeded",
        )
    )
    assert env.task_status == "succeeded"
    assert env.winner_rule == "default_success"
    assert env.quality_gate["pass"] is True


def test_complex_success() -> None:
    env = finalize_turn_exit(
        TurnFacts(
            router_lane="kb",
            effective_mode="complex",
            executor_profile="complex",
            primary_path_candidate="agno_basic_v2_kb",
            legacy_task_status="succeeded",
        )
    )
    assert env.task_status == "succeeded"
    assert "kb" in env.primary_path or env.primary_path == "complex_rag_answer"


def test_async_pending() -> None:
    env = finalize_turn_exit(
        TurnFacts(
            router_lane="video",
            effective_mode="async",
            async_pending=True,
            answer_type="async_pending",
            legacy_task_status="pending",
        )
    )
    assert env.task_status == "pending"
    assert env.winner_rule == "async_pending"


def test_approval_blocked() -> None:
    env = finalize_turn_exit(
        TurnFacts(
            approval=ApprovalExitSignal(blocked=True),
            answer_type="approval_blocked",
            legacy_task_status="blocked",
        )
    )
    assert env.task_status == "blocked"
    assert env.winner_rule == "approval_blocked"


def test_commit_executed_success() -> None:
    env = finalize_turn_exit(
        TurnFacts(
            approval=ApprovalExitSignal(commit_executed=True, commit_success=True),
            answer_type="commit_executed",
            legacy_task_status="completed",
        )
    )
    assert env.task_status == "succeeded"
    assert env.winner_rule == "commit_executed"


def test_commit_executed_failure() -> None:
    env = finalize_turn_exit(
        TurnFacts(
            approval=ApprovalExitSignal(commit_executed=True, commit_success=False),
            answer_type="commit_executed",
            legacy_task_status="failed",
            pipeline_ok=False,
        )
    )
    assert env.task_status == "failed"


def test_soft_limitation_not_partial() -> None:
    env = finalize_turn_exit(
        TurnFacts(
            pending_kind=PendingKind.NONE,
            limitations=("首响预算不足，部分证据尚未补齐。",),
            legacy_task_status="succeeded",
        )
    )
    assert env.task_status == "succeeded"
    assert env.pending_kind is None


def test_hard_failure_failed() -> None:
    env = finalize_turn_exit(
        TurnFacts(
            hard_failure=True,
            legacy_task_status="failed",
            pipeline_ok=False,
        )
    )
    assert env.task_status == "failed"
    assert env.winner_rule == "hard_failure"


def test_partial_pending_maps_partial() -> None:
    env = finalize_turn_exit(
        TurnFacts(
            pending_kind=PendingKind.PARTIAL_PENDING,
            legacy_task_status="partial",
        )
    )
    assert env.task_status == "partial"
    assert env.pending_kind == PendingKind.PARTIAL_PENDING.value


def test_quality_gate_empty_answer_blocks() -> None:
    env = finalize_turn_exit(
        TurnFacts(
            quality_gate=QualityGateResult(pass_=False, reason_codes=("answer_empty",)),
            legacy_task_status="succeeded",
        )
    )
    assert env.task_status == "failed"
    assert env.winner_rule == "quality_gate_block"


def test_quality_gate_need_second_round_does_not_force_failed() -> None:
    env = finalize_turn_exit(
        TurnFacts(
            quality_gate=QualityGateResult(
                pass_=False,
                need_second_round=True,
                reason_codes=("answer_too_shallow",),
            ),
            legacy_task_status="succeeded",
        )
    )
    assert env.task_status == "succeeded"
    assert env.quality_gate["need_second_round"] is True


def test_conflicting_signals_approval_wins() -> None:
    env = finalize_turn_exit(
        TurnFacts(
            approval=ApprovalExitSignal(blocked=True),
            async_pending=True,
            pending_kind=PendingKind.FAST_PENDING,
            legacy_task_status="pending",
        )
    )
    assert env.task_status == "blocked"
    assert env.winner_rule == "approval_blocked"


def test_shadow_compare_normalizes_completed() -> None:
    old = {
        "task_status": "completed",
        "primary_path": "approval_gate",
        "extra": {"mode": "fast", "pending_kind": None},
    }
    env = finalize_turn_exit(
        TurnFacts(
            approval=ApprovalExitSignal(commit_executed=True, commit_success=True),
            answer_type="commit_executed",
            legacy_task_status="completed",
        )
    )
    shadow = compare_exit_shadow(old=old, envelope=env)
    assert shadow["match"] is True
    assert not shadow["diff_fields"]


def test_single_write_applies_canonical_exit_when_shadow_diff() -> None:
    from application.chat.turn_exit_gate import apply_turn_exit_to_chat_turn
    from config import feature_flags

    old_flags = dict(feature_flags.FEATURE_FLAGS)
    try:
        feature_flags.FEATURE_FLAGS["ENABLE_TURN_EXIT_GATE_SHADOW"] = True
        result = apply_turn_exit_to_chat_turn(
            {
                "task_status": "succeeded",
                "primary_path": "legacy_path",
                "extra": {
                    "mode": "fast",
                    EXIT_SIGNAL_PENDING_KIND: PendingKind.FAST_PENDING.value,
                },
                "answer_type": "fast_pending",
                "pipeline_ok": True,
            },
            effective_mode="fast",
        )
        assert result["task_status"] == "pending"
        shadow = (result.get("extra") or {}).get("trace", {}).get("exit_shadow") or {}
        assert shadow.get("match") is False
        assert result["extra"].get("pending_kind") == PendingKind.FAST_PENDING.value
    finally:
        feature_flags.FEATURE_FLAGS.clear()
        feature_flags.FEATURE_FLAGS.update(old_flags)


def test_default_shadow_off_no_exit_shadow_in_trace() -> None:
    from application.chat.turn_exit_gate import apply_turn_exit_to_chat_turn
    from config import feature_flags

    old_flags = dict(feature_flags.FEATURE_FLAGS)
    try:
        feature_flags.FEATURE_FLAGS["ENABLE_TURN_EXIT_GATE_SHADOW"] = False
        result = apply_turn_exit_to_chat_turn(
            {
                "task_status": "succeeded",
                "primary_path": "direct_llm",
                "extra": {"mode": "fast"},
                "pipeline_ok": True,
            },
            effective_mode="fast",
        )
        trace = (result.get("extra") or {}).get("trace") or {}
        assert "exit_shadow" not in trace
    finally:
        feature_flags.FEATURE_FLAGS.clear()
        feature_flags.FEATURE_FLAGS.update(old_flags)


def test_exit_compare_fields_fixed() -> None:
    assert EXIT_COMPARE_FIELDS == ("task_status", "pending_kind", "primary_path", "mode")
