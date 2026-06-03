"""S7c — V17 bundle fields mapped to PendingKind (§7.6.1)."""
from __future__ import annotations

from dataclasses import replace
from threading import Lock
from types import SimpleNamespace

import pytest

from agents.main_agent.schema import AgnoCollaborationPlan, MainXiezuoPan
from agents.middle_agent.schema import AgnoMaterialBundle, CailiaoPan
from application.chat.complex_pending_mapping import (
    resolve_bundle_pending_kind,
    resolve_final_task_status,
)
from application.chat.history_buffer import ChatTurnDeps
from application.chat.pending_kind import PendingKind
from application.chat.response_assembly import build_extra
from application.chat.run_chat_turn import run_agno_chat_turn_impl
from config import feature_flags
from schemas import MainDecision


def _bundle(**overrides) -> AgnoMaterialBundle:
    base = AgnoMaterialBundle(
        knowledge_block=None,
        web_block=None,
        trace=[],
        knowledge_adequate=False,
        material_still_insufficient=False,
        web_judgment_reason="explicit_only",
        kb_evidence_tier="none",
        insufficiency_signal="none",
        cailiao_pan=CailiaoPan(
            gou=True,
            kb_qiangdu=0.0,
            bukong_xinhao="ok",
            laiyuan_zhu="kb",
            use_kb=False,
            use_web=False,
            que_shenme="none",
            xia_yi_bu="zhi_da",
        ),
    )
    return replace(base, **overrides)


def test_hard_material_gap_maps_partial_pending() -> None:
    bundle = _bundle(
        material_sufficiency="insufficient",
        material_still_insufficient=True,
        insufficiency_signal="still_empty_after_gather",
    )
    assert resolve_bundle_pending_kind(bundle=bundle) == PendingKind.PARTIAL_PENDING


def test_soft_material_insufficiency_does_not_map_partial_pending() -> None:
    bundle = _bundle(
        material_sufficiency="insufficient",
        material_still_insufficient=True,
        insufficiency_signal="need_compare",
    )
    assert resolve_bundle_pending_kind(bundle=bundle) == PendingKind.NONE


def test_feedback_request_maps_processing_pending() -> None:
    bundle = _bundle(
        feedback_request={"request_type": "more_web_material", "reason": "need evidence"},
        used_rounds=[0],
    )
    assert resolve_bundle_pending_kind(bundle=bundle) == PendingKind.PROCESSING_PENDING


def test_critic_revision_required_maps_partial_pending() -> None:
    bundle = _bundle(critic_check={"revision_required": True, "safe_to_answer": False})
    assert resolve_bundle_pending_kind(bundle=bundle) == PendingKind.PARTIAL_PENDING


def test_pending_item_maps_material_pending() -> None:
    pending_item = SimpleNamespace(
        commit_status="pending",
        extract_status="ok",
        pending_id="pend-1",
        source_type="web_url",
    )
    bundle = _bundle(pending_item=pending_item)
    assert resolve_bundle_pending_kind(bundle=bundle) == PendingKind.MATERIAL_PENDING


def test_session_pending_overrides_bundle() -> None:
    bundle = _bundle(material_sufficiency="insufficient", material_still_insufficient=True)
    assert (
        resolve_bundle_pending_kind(
            bundle=bundle,
            session_pending=PendingKind.PROCESSING_PENDING,
        )
        == PendingKind.PROCESSING_PENDING
    )


def test_resolve_final_task_status_prefers_pending_kind() -> None:
    assert (
        resolve_final_task_status(
            pending_kind=PendingKind.PARTIAL_PENDING,
            hard_deadline_limited=True,
            bundle_pending_item_present=True,
        )
        == "partial"
    )


def test_resolve_final_task_status_maps_deadline_pending_without_kind() -> None:
    assert (
        resolve_final_task_status(
            pending_kind=PendingKind.NONE,
            hard_deadline_limited=True,
            bundle_pending_item_present=True,
        )
        == "pending"
    )


def test_build_extra_emits_pending_kind_when_flag_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_COMPLEX_PENDING_KIND_V2", True)
    bundle = _bundle(
        feedback_request={"request_type": "more_web_material"},
        used_rounds=[0],
        critic_check={"revision_required": False, "safe_to_answer": True},
    )
    history = SimpleNamespace(session_id="s1", turns=0, has_prev_video=False, prev_video=None, pending_video_text=None)
    plan = AgnoCollaborationPlan(
        decision=MainDecision(task_id="t1", task_status="routed"),
        force_skip_evidence=False,
        web_supplement_mode="explicit_only",
        answer_composition="default",
        xiezuo_pan=MainXiezuoPan(
            renwu_lei="hunhe",
            zhengju_need=True,
            allow_kb=True,
            allow_web=True,
            fengxian_yinzi=0.5,
            celue_tag="complex",
        ),
    )
    extra = build_extra(
        "比较方案",
        plan,
        bundle,
        MainDecision(task_id="t1", task_status="routed"),
        "部分结论",
        SimpleNamespace(
            answer_agent=SimpleNamespace(
                pan=lambda *_a, **_k: SimpleNamespace(lane="general", primary_path="complex"),
                xiezuo_extra=lambda *_a, **_k: {},
            ),
            path_fingerprint=lambda *_a, **_k: "fp",
            nodes_contract=lambda *_a, **_k: {},
        ),
        use_knowledge=False,
        knowledge_block=None,
        web_block=None,
        collab_trace=[],
        history_snapshot=history,
    )
    from application.chat.exit_signals import EXIT_SIGNAL_PENDING_KIND

    assert extra.get(EXIT_SIGNAL_PENDING_KIND) == PendingKind.PROCESSING_PENDING.value
    assert "pending_kind" not in extra
    assert extra["critic_check"] == {"revision_required": False, "safe_to_answer": True}


def test_complex_turn_exposes_pending_kind_in_response(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_COMPLEX_PENDING_KIND_V2", True)
    monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_THREE_AGENT_AUTONOMY", True)

    plan = AgnoCollaborationPlan(
        decision=MainDecision(task_id="s7c-map", task_status="routed"),
        force_skip_evidence=False,
        web_supplement_mode="explicit_only",
        answer_composition="default",
        xiezuo_pan=MainXiezuoPan(
            renwu_lei="hunhe",
            zhengju_need=True,
            allow_kb=True,
            allow_web=True,
            fengxian_yinzi=0.5,
            celue_tag="complex",
        ),
        job_type="multi_source_compare",
        max_rounds=2,
        budget_policy={"budget_remaining_ms": 0, "llm_calls_remaining": 0, "tool_calls_remaining": 0},
    )
    bundle = _bundle(
        knowledge_block="KB",
        web_block="WEB",
        material_still_insufficient=True,
        material_sufficiency="insufficient",
        insufficiency_signal="need_compare",
    )

    deps = ChatTurnDeps(
        histories={},
        session_prev_video={},
        session_pending_video={},
        lock=Lock(),
        main_agent=SimpleNamespace(pan=lambda *_a, **_k: plan),
        middle_agent=SimpleNamespace(caipan=lambda *_a, **_k: bundle),
        answer_agent=SimpleNamespace(
            pan=lambda *_a, **_k: SimpleNamespace(lane="general", primary_path="complex"),
            xiezuo_extra=lambda *_a, **_k: {},
            review_multisource=lambda *_a, **_k: {"feedback_request": None},
        ),
        run_basic_qa=lambda *_a, **_k: "预算内首答",
        path_fingerprint=lambda *_a, **_k: "fp",
        nodes_contract=lambda *_a, **_k: {},
    )

    out = run_agno_chat_turn_impl(
        "结合知识库和网页比较方案",
        session_id="sess-s7c",
        use_knowledge=True,
        deps=deps,
    )
    assert out["extra"]["pending_kind"] == PendingKind.PARTIAL_PENDING.value
    assert out["task_status"] == "partial"
    assert isinstance(out["extra"].get("limitations"), list)
