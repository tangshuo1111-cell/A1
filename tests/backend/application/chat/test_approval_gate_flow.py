"""Tests for approval_gate_flow orchestrator."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from application.chat.approval_gate_flow import (
    build_approval_blocked_answer,
    evaluate_turn_approval,
)
from config import feature_flags


@pytest.fixture(autouse=True)
def _enable_approval_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_APPROVAL_GATE_V1", True)


def test_commit_without_pending_blocked():
    with patch(
        "services.capabilities.knowledge.pending_ingestion_service.list_pending",
        return_value=[],
    ):
        result = evaluate_turn_approval(
            message="请保存到知识库",
            session_id="sess-1",
            confirm_long_web_video_asr=False,
            use_knowledge=False,
        )
    assert result.blocked is True
    assert result.kind == "pending_commit"
    assert "pending" in build_approval_blocked_answer(result).lower() or "资料" in build_approval_blocked_answer(result)


def test_long_video_requires_confirmation():
    result = evaluate_turn_approval(
        message="总结这个长视频 https://youtube.com/watch?v=abc",
        session_id="sess-1",
        confirm_long_web_video_asr=False,
        use_knowledge=False,
    )
    assert result.blocked is True
    assert result.kind == "long_video_asr"


def test_long_video_confirmed_passes():
    result = evaluate_turn_approval(
        message="总结这个长视频 https://youtube.com/watch?v=abc",
        session_id="sess-1",
        confirm_long_web_video_asr=True,
        use_knowledge=False,
    )
    assert result.blocked is False


def test_commit_with_pending_executes_via_try_execute(monkeypatch: pytest.MonkeyPatch) -> None:
    from application.chat.approval_gate_flow import try_execute_commit_turn
    from services.capabilities.knowledge.pending_ingestion_service import CommitResult

    monkeypatch.setattr(
        "services.capabilities.knowledge.pending_ingestion_service.list_pending",
        lambda *_a, **_k: [object()],
    )
    monkeypatch.setattr(
        "services.capabilities.knowledge.pending_ingestion_service.commit_most_recent_pending",
        lambda *_a, **_k: CommitResult(
            success=True,
            pending_id="p1",
            source_id="doc:1",
            chunk_count=3,
            title="样例文档",
        ),
    )
    out = try_execute_commit_turn(
        message="请保存到知识库",
        session_id="sess-commit",
        request_id="req-1",
        elapsed_ms=12,
        ingress=None,
    )
    assert out is not None
    assert out["answer_type"] == "commit_executed"
    assert out["extra"]["approval_gate.executed"] is True
    assert out["extra"]["material_layer_used"] == "committed"
    assert "样例文档" in out["answer"]
