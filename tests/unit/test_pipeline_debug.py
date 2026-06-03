"""core.pipeline_debug：从 ChatFlowResult 推导排查字段。"""

from __future__ import annotations

from datetime import UTC, datetime

from core.pipeline_debug import build_pipeline_observability
from schemas import (
    AnswerResult,
    ChatFlowResult,
    EvidencePack,
    MainDecision,
    TaskInput,
)


def _task() -> TaskInput:
    return TaskInput(
        task_id="t1",
        user_query="q",
        clean_query="q",
        created_at=datetime.now(UTC),
    )


def test_pipeline_ok_direct_style_done():
    dec = MainDecision(
        task_id="t1",
        answer_channel="direct",
        router_source="rules",
    )
    ev = EvidencePack(task_id="t1", gap_categories=["skipped_middle"])
    ans = AnswerResult(
        task_id="t1",
        final_answer="hi",
        task_status="done",
    )
    r = ChatFlowResult(task=_task(), decision=dec, evidence=ev, answer=ans, extra={"primary_path": "none"})
    obs = build_pipeline_observability(r)
    assert obs["pipeline_ok"] is True
    assert obs["error_layer"] == "none"


def test_zero_rag_marks_retrieval():
    dec = MainDecision(task_id="t1", answer_channel="kb", router_source="rules")
    ev = EvidencePack(
        task_id="t1",
        gap_categories=["zero_rag_hit"],
        evidence_state="not_found",
    )
    ans = AnswerResult(
        task_id="t1",
        final_answer="x",
        task_status="partial",
        has_insufficient_info_notice=True,
    )
    r = ChatFlowResult(task=_task(), decision=dec, evidence=ev, answer=ans, extra={"primary_path": "rag"})
    obs = build_pipeline_observability(r)
    assert obs["pipeline_ok"] is False
    assert obs["error_layer"] == "retrieval"
    assert obs["pipeline_error_code"] == "ZERO_RAG_HIT"
    assert obs["pipeline_hint_zh"]


def test_middle_exception_workflow():
    dec = MainDecision(task_id="t1", answer_channel="kb", router_source="rules")
    ev = EvidencePack(
        task_id="t1",
        gap_categories=["middle_exception"],
        evidence_state="channel_failed",
    )
    ans = AnswerResult(task_id="t1", final_answer="资料收集异常", task_status="partial")
    r = ChatFlowResult(task=_task(), decision=dec, evidence=ev, answer=ans, extra={})
    obs = build_pipeline_observability(r)
    assert obs["error_layer"] == "workflow"
    assert obs["pipeline_error_code"] == "MIDDLE_EXCEPTION"
