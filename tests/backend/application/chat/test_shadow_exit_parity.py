"""Prove exit_shadow.match across primary chat exit builders (step 1)."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from application.chat.approval_gate import ApprovalGateResult
from application.chat.approval_gate_flow import (
    build_approval_blocked_turn_result,
    build_commit_executed_turn_result,
)
from application.chat.async_entry import assemble_async_pending_result
from application.chat.fast_path_entry import build_fast_result
from application.chat.pending_kind import PendingKind
from config import feature_flags


def _shadow(result: dict) -> dict:
    extra = result.get("extra") or {}
    trace = extra.get("trace") or {}
    return trace.get("exit_shadow") or {}


@pytest.fixture(autouse=True)
def _shadow_debug_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_TURN_EXIT_GATE_SHADOW", True)


def test_shadow_parity_fast_succeeded() -> None:
    result = build_fast_result(
        answer="ok",
        session_id="s-shadow",
        request_id="r1",
        elapsed_ms=10,
        extra={"lane": "general", "fast_path": "direct_llm"},
    )
    sh = _shadow(result)
    assert sh.get("match") is True, sh.get("diff_fields")


def test_shadow_parity_fast_pending() -> None:
    result = build_fast_result(
        answer="pending",
        session_id="s-shadow",
        request_id="r2",
        elapsed_ms=10,
        extra={
            "lane": "video",
            "fast_path": "video_fast_background_hint",
            "task_id": "task-1",
            "pending_kind": PendingKind.FAST_PENDING.value,
        },
    )
    sh = _shadow(result)
    assert sh.get("match") is True, sh.get("diff_fields")


def test_shadow_parity_async_pending() -> None:
    result = assemble_async_pending_result(
        lane="video",
        task_id="task-async-1",
        queue_backend="memory",
        answer="queued",
        session_id="s-async",
        request_id="r3",
        elapsed_ms=20,
        router_source="rule",
        router_confidence=0.9,
        router_fallback=False,
        router_decision_ms=5,
    )
    sh = _shadow(result)
    assert sh.get("match") is True, sh.get("diff_fields")


def test_shadow_parity_approval_blocked() -> None:
    ingress = SimpleNamespace(lane="video", mode="async")
    result = build_approval_blocked_turn_result(
        result=ApprovalGateResult(
            required=True,
            blocked=True,
            kind="long_video_asr",
            reason="need confirm",
        ),
        message="总结长视频",
        session_id="s-ap",
        request_id="r4",
        elapsed_ms=15,
        ingress=ingress,
    )
    sh = _shadow(result)
    assert sh.get("match") is True, sh.get("diff_fields")
    assert result["extra"]["mode"] == "blocked"


def test_shadow_parity_commit_success() -> None:
    commit = SimpleNamespace(
        success=True,
        pending_id="p1",
        source_id="src1",
        chunk_count=2,
        error_code="",
        title="doc",
        source_type="pdf",
    )
    result = build_commit_executed_turn_result(
        message="确认入库",
        session_id="s-commit",
        request_id="r5",
        elapsed_ms=12,
        ingress=None,
        commit_result=commit,
    )
    sh = _shadow(result)
    assert sh.get("match") is True, sh.get("diff_fields")


def test_shadow_parity_commit_failure() -> None:
    commit = SimpleNamespace(
        success=False,
        pending_id="p1",
        source_id="",
        chunk_count=0,
        error_code="commit_failed",
        title="",
        source_type="pdf",
    )
    result = build_commit_executed_turn_result(
        message="确认入库",
        session_id="s-commit-f",
        request_id="r6",
        elapsed_ms=12,
        ingress=None,
        commit_result=commit,
    )
    sh = _shadow(result)
    assert sh.get("match") is True, sh.get("diff_fields")
