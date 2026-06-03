from __future__ import annotations

from threading import Lock
from types import SimpleNamespace

from agents.answer_agent import AnswerAgent
from agents.main_agent.schema import AgnoCollaborationPlan, MainXiezuoPan
from agents.middle_agent.schema import AgnoMaterialBundle, CailiaoPan, EvidenceEnvelope
from application.chat.run_chat_turn import ChatTurnDeps, run_agno_chat_turn_impl
from schemas import MainDecision


def _plan(*, budget_policy: dict) -> AgnoCollaborationPlan:
    return AgnoCollaborationPlan(
        decision=MainDecision(task_id="p8-budget", task_status="routed"),
        force_skip_evidence=False,
        web_supplement_mode="on_kb_miss_or_hint",
        answer_composition="default",
        xiezuo_pan=MainXiezuoPan(
            renwu_lei="zhishu",
            zhengju_need=True,
            allow_kb=True,
            allow_web=True,
            fengxian_yinzi=0.5,
            celue_tag="kb_web",
        ),
        needs_retrieval=True,
        retrieval_strategy="auto",
        answer_mode="knowledge_grounded",
        tools_allowed=("fetch_web",),
        max_rounds=1,
        original_user_intent="请根据知识库和网页证据回答：项目代号是什么",
        budget_policy=budget_policy,
        remaining_ms_hint=int(budget_policy.get("budget_remaining_ms", 20_000)),
    )


def _bundle() -> AgnoMaterialBundle:
    return AgnoMaterialBundle(
        knowledge_block="",
        web_block="",
        trace=[],
        knowledge_adequate=False,
        material_still_insufficient=True,
        web_judgment_reason="skip",
        kb_evidence_tier="none",
        insufficiency_signal="still_empty_after_gather",
        cailiao_pan=CailiaoPan(
            gou=False,
            kb_qiangdu=0.0,
            bukong_xinhao="que",
            laiyuan_zhu="wu",
            use_kb=True,
            use_web=False,
            que_shenme="liangzhe",
            xia_yi_bu="bu_wang",
        ),
        material_sufficiency="insufficient",
        evidence_envelopes=[EvidenceEnvelope(source_type="kb", status="failed", error_code="kb_no_match")],
        critic_check={
            "critic_check_id": "critic_p8_budget",
            "revision_required": True,
            "safe_to_answer": False,
            "limitations": ["当前没有成功证据来源，最终回答必须保守说明。"],
        },
    )


def _deps(plan: AgnoCollaborationPlan) -> ChatTurnDeps:
    return ChatTurnDeps(
        histories={},
        session_prev_video={},
        session_pending_video={},
        lock=Lock(),
        main_agent=SimpleNamespace(pan=lambda *a, **k: plan),
        middle_agent=SimpleNamespace(caipan=lambda *a, **k: _bundle()),
        answer_agent=AnswerAgent(),
        run_basic_qa=lambda *a, **k: "保守回答",
        path_fingerprint=lambda *a, **k: "fp",
        nodes_contract=lambda tr: {},
    )


def test_llm_budget_exhausted_stops_autonomy_loop() -> None:
    out = run_agno_chat_turn_impl(
        "请根据知识库和网页证据回答：项目代号是什么",
        session_id="p8-llm-exhausted",
        deps=_deps(_plan(budget_policy={"llm_calls_remaining": 0, "tool_calls_remaining": 2, "budget_remaining_ms": 8000})),
    )
    extra = out["extra"]
    assert extra["stop_reason"] == "llm_calls_exhausted"
    assert extra["loop_total_rounds"] == 1
    assert extra["more_evidence_requested"] is False


def test_tool_budget_exhausted_blocks_round1_fetch(monkeypatch) -> None:
    called = {"web": 0}

    def _never(*_a, **_k):
        called["web"] += 1
        return "[Web检索] 不应被调用"

    monkeypatch.setattr("application.chat.run_chat_turn.agno_web_service.fetch_web_evidence_block", _never)
    out = run_agno_chat_turn_impl(
        "请根据知识库和网页证据回答：项目代号是什么",
        session_id="p8-tool-exhausted",
        deps=_deps(_plan(budget_policy={"llm_calls_remaining": 2, "tool_calls_remaining": 0, "budget_remaining_ms": 8000})),
    )
    extra = out["extra"]
    assert called["web"] == 0
    assert extra["stop_reason"] == "tool_calls_exhausted"
