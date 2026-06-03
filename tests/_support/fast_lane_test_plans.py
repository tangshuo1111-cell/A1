"""Minimal Main/Middle stubs for fast-lane migration tests."""
from __future__ import annotations

from threading import Lock
from types import SimpleNamespace

from agents.main_agent.schema import AgnoCollaborationPlan, MainXiezuoPan
from agents.middle_agent.schema import AgnoMaterialBundle, CailiaoPan
from application.chat.history_buffer import ChatTurnDeps
from schemas import MainDecision


def minimal_complex_plan(*, task_id: str = "fast-lane-stub") -> AgnoCollaborationPlan:
    return AgnoCollaborationPlan(
        decision=MainDecision(task_id=task_id, task_status="routed"),
        force_skip_evidence=False,
        web_supplement_mode="explicit_only",
        answer_composition="default",
        xiezuo_pan=MainXiezuoPan(
            renwu_lei="zhishu",
            zhengju_need=False,
            allow_kb=True,
            allow_web=False,
            fengxian_yinzi=0.2,
            celue_tag="test",
        ),
        needs_retrieval=False,
        retrieval_strategy="none",
        answer_mode="direct",
        tools_allowed=(),
        max_rounds=1,
        original_user_intent="stub",
    )


def minimal_complex_bundle() -> AgnoMaterialBundle:
    return AgnoMaterialBundle(
        knowledge_block="",
        web_block="",
        trace=[],
        knowledge_adequate=True,
        material_still_insufficient=False,
        web_judgment_reason="skip",
        kb_evidence_tier="none",
        insufficiency_signal="none",
        cailiao_pan=CailiaoPan(
            gou=True,
            kb_qiangdu=0.0,
            bukong_xinhao="zu",
            laiyuan_zhu="wu",
            use_kb=False,
            use_web=False,
            que_shenme="wu",
            xia_yi_bu="bu_wang",
        ),
    )


def fast_lane_deps(*, answer: str = "stub-answer") -> ChatTurnDeps:
    plan = minimal_complex_plan()
    bundle = minimal_complex_bundle()
    return ChatTurnDeps(
        histories={},
        session_prev_video={},
        session_pending_video={},
        lock=Lock(),
        main_agent=SimpleNamespace(pan=lambda *a, **k: plan),
        middle_agent=SimpleNamespace(caipan=lambda *a, **k: bundle),
        answer_agent=SimpleNamespace(
            xiezuo_extra=lambda *a, **k: {},
            pan=lambda *a, **k: SimpleNamespace(lane="general", primary_path="fast"),
        ),
        run_basic_qa=lambda *a, **k: answer,
        path_fingerprint=lambda *a, **k: "fp",
        nodes_contract=lambda trace: {},
    )
