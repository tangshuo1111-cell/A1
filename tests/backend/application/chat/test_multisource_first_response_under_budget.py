"""S7c — multisource complex path returns under budget with partial_pending (§6.2.1)."""
from __future__ import annotations

import time
from threading import Lock
from types import SimpleNamespace

import pytest

from agents.main_agent.schema import AgnoCollaborationPlan, MainXiezuoPan
from agents.middle_agent.schema import AgnoMaterialBundle, CailiaoPan
from application.chat.budget_clock import SLA_BUDGET_MS, BudgetClock
from application.chat.executors.complex.complex_path_impl import run_multisource_round0_answer
from application.chat.history_buffer import ChatTurnDeps
from application.chat.pending_kind import PendingKind
from application.chat.run_chat_turn import run_agno_chat_turn_impl
from config import feature_flags
from schemas import MainDecision


def _multisource_plan(*, budget_remaining_ms: int = 0) -> AgnoCollaborationPlan:
    return AgnoCollaborationPlan(
        decision=MainDecision(task_id="s7c-ms", task_status="routed"),
        force_skip_evidence=False,
        web_supplement_mode="explicit_only",
        answer_composition="default",
        xiezuo_pan=MainXiezuoPan(
            renwu_lei="hunhe",
            zhengju_need=True,
            allow_kb=True,
            allow_web=True,
            fengxian_yinzi=0.8,
            celue_tag="complex",
        ),
        job_type="multi_source_compare",
        max_rounds=2,
        needs_retrieval=True,
        retrieval_strategy="auto",
        answer_mode="knowledge_grounded",
        tools_allowed=("fetch_web",),
        original_user_intent="比较三个来源",
        budget_policy={
            "budget_remaining_ms": budget_remaining_ms,
            "llm_calls_remaining": 0,
            "tool_calls_remaining": 0,
        },
    )


def _multisource_bundle() -> AgnoMaterialBundle:
    return AgnoMaterialBundle(
        knowledge_block="知识库：方案 A 成本低。",
        web_block="网页：方案 B 上线快。",
        trace=[],
        knowledge_adequate=False,
        material_still_insufficient=True,
        web_judgment_reason="explicit_only",
        kb_evidence_tier="partial",
        insufficiency_signal="need_compare",
        cailiao_pan=CailiaoPan(
            gou=False,
            kb_qiangdu=0.5,
            bukong_xinhao="que",
            laiyuan_zhu="mixed",
            use_kb=True,
            use_web=True,
            que_shenme="compare",
            xia_yi_bu="bu_wang",
        ),
    )


def test_multisource_first_response_under_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_COMPLEX_PENDING_KIND_V2", True)
    monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_THREE_AGENT_AUTONOMY", True)
    monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_BUDGET_CLOCK_V2", True)

    plan = _multisource_plan(budget_remaining_ms=0)
    bundle = _multisource_bundle()
    clock = BudgetClock(
        started_at=time.perf_counter(),
        deadline_at=time.perf_counter() + 0.001,
        total_budget_ms=SLA_BUDGET_MS,
    )

    deps = ChatTurnDeps(
        histories={},
        session_prev_video={},
        session_pending_video={},
        lock=Lock(),
        main_agent=SimpleNamespace(pan=lambda *_a, **_k: plan),
        middle_agent=SimpleNamespace(caipan=lambda *_a, **_k: bundle),
        answer_agent=SimpleNamespace(
            review_multisource=lambda *_a, **_k: {
                "feedback_request": {
                    "request_type": "more_web_material",
                    "reason": "需要更多证据",
                }
            },
        ),
        run_basic_qa=lambda *_a, **_k: "在预算内给出保守首答。",
        path_fingerprint=lambda *_a, **_k: "fp",
        nodes_contract=lambda *_a, **_k: {},
    )

    t0 = time.perf_counter()
    out_bundle, answer = run_multisource_round0_answer(
        "结合知识库、网页和文档比较方案",
        plan,
        bundle,
        deps,
        use_knowledge=True,
        history_snapshot=SimpleNamespace(
            session_id="sess-ms",
            turns=0,
            has_prev_video=False,
            prev_video=None,
            pending_video_text=None,
        ),
        session_id="sess-ms",
        context_block="",
        knowledge_block=bundle.knowledge_block,
        web_block=bundle.web_block,
        main_dec=plan.decision,
        v13_text_content=None,
        v13_title=None,
        v13_file_content=None,
        budget_clock=clock,
    )
    elapsed_ms = int((time.perf_counter() - t0) * 1000)

    assert answer == "在预算内给出保守首答。"
    assert elapsed_ms < SLA_BUDGET_MS
    assert out_bundle.execution_status == "partial"
    assert out_bundle.negotiation_trace.get("complex_pending_kind") == PendingKind.PARTIAL_PENDING.value
    assert out_bundle.negotiation_trace.get("v17_partial_status") == "budget_exhausted"
    assert any("预算" in item for item in (out_bundle.answer_limitations or []))


def test_multisource_turn_task_status_partial_via_run_chat_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_COMPLEX_PENDING_KIND_V2", True)
    monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_THREE_AGENT_AUTONOMY", True)

    plan = _multisource_plan(budget_remaining_ms=0)
    bundle = _multisource_bundle()

    deps = ChatTurnDeps(
        histories={},
        session_prev_video={},
        session_pending_video={},
        lock=Lock(),
        main_agent=SimpleNamespace(pan=lambda *_a, **_k: plan),
        middle_agent=SimpleNamespace(caipan=lambda *_a, **_k: bundle),
        answer_agent=SimpleNamespace(
            pan=lambda *_a, **_k: SimpleNamespace(lane="general", primary_path="complex_autonomy"),
            xiezuo_extra=lambda *_a, **_k: {},
            review_multisource=lambda *_a, **_k: {"feedback_request": None},
        ),
        run_basic_qa=lambda *_a, **_k: "综合比较后的首答。",
        path_fingerprint=lambda *_a, **_k: "fp",
        nodes_contract=lambda *_a, **_k: {},
    )

    out = run_agno_chat_turn_impl(
        "结合知识库、网页和文档比较方案",
        session_id="sess-ms-full",
        use_knowledge=True,
        deps=deps,
    )

    assert out["answer"] == "综合比较后的首答。"
    assert out["task_status"] == "partial"
    assert out["extra"]["pending_kind"] == PendingKind.PARTIAL_PENDING.value
    assert out["extra"].get("limitations")
