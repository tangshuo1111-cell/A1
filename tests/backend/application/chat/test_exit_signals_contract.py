"""Assembly emits exit_signal_* only; TurnExitGate owns canonical exit keys."""
from __future__ import annotations

from types import SimpleNamespace

from agents.main_agent.schema import AgnoCollaborationPlan, MainDecision, MainXiezuoPan
from agents.middle_agent.schema import AgnoMaterialBundle, CailiaoPan
from application.chat.exit_signals import (
    EXIT_SIGNAL_PENDING_KIND,
    EXIT_SIGNAL_PRIMARY_PATH,
)
from application.chat.pending_kind import PendingKind
from application.chat.response_assembly import build_extra
from application.chat.turn_exit_gate import apply_turn_exit_to_chat_turn
from application.chat.turn_facts import TurnFacts
from rag.pending_schema import SOURCE_TYPE_WEB_URL, PendingKnowledgeItem, SourcePayload


def _minimal_build_extra(*, pending_item: object | None = None) -> dict:
    bundle = AgnoMaterialBundle(
        knowledge_block="kb",
        web_block=None,
        trace=[],
        knowledge_adequate=True,
        material_still_insufficient=False,
        web_judgment_reason="explicit_only",
        kb_evidence_tier="strong",
        insufficiency_signal="ok",
        pending_item=pending_item,
        cailiao_pan=CailiaoPan(
            gou=True,
            kb_qiangdu=0.8,
            bukong_xinhao="ok",
            laiyuan_zhu="kb",
            use_kb=True,
            use_web=False,
            que_shenme="none",
            xia_yi_bu="zhi_da",
        ),
    )
    plan = AgnoCollaborationPlan(
        decision=MainDecision(task_id="sig-1", task_status="routed"),
        force_skip_evidence=False,
        web_supplement_mode="explicit_only",
        answer_composition="default",
        xiezuo_pan=MainXiezuoPan(
            renwu_lei="hunhe",
            zhengju_need=True,
            allow_kb=True,
            allow_web=False,
            fengxian_yinzi=0.5,
            celue_tag="complex",
        ),
    )
    history = SimpleNamespace(
        session_id="s",
        turns=0,
        has_prev_video=False,
        prev_video=None,
        pending_video_text=None,
    )
    deps = SimpleNamespace(
        answer_agent=SimpleNamespace(
            pan=lambda *_a, **_k: SimpleNamespace(lane="kb", primary_path="agno_basic_v2_kb"),
            xiezuo_extra=lambda *_a, **_k: {},
        ),
        path_fingerprint=lambda *_a, **_k: "fp",
        nodes_contract=lambda *_a, **_k: {},
    )
    return build_extra(
        "q",
        plan,
        bundle,
        plan.decision,
        "answer",
        deps,
        use_knowledge=True,
        knowledge_block="kb",
        web_block=None,
        collab_trace=[],
        history_snapshot=history,
    )


def test_build_extra_writes_path_signal_not_canonical_primary_path() -> None:
    extra = _minimal_build_extra()
    assert extra.get(EXIT_SIGNAL_PRIMARY_PATH) == "agno_basic_v2_kb"
    assert "primary_path" not in extra


def test_build_extra_writes_pending_signal_not_canonical_pending_kind() -> None:
    pending_item = PendingKnowledgeItem.create(
        session_id="sess-sig",
        payload=SourcePayload(
            source_type=SOURCE_TYPE_WEB_URL,
            source_id="web:sig",
            title="Pending",
            text="preview",
            metadata={"source_id": "web:sig"},
            raw_source="https://example.com/p",
        ),
        parser_name="fetch_web",
        extract_status="queued",
    )
    extra = _minimal_build_extra(pending_item=pending_item)
    assert extra.get(EXIT_SIGNAL_PENDING_KIND) == PendingKind.PROCESSING_PENDING.value
    assert "pending_kind" not in extra


def test_gate_overwrites_canonical_fields_from_signals() -> None:
    extra = _minimal_build_extra()
    path = str(extra.get(EXIT_SIGNAL_PRIMARY_PATH) or "agno_basic_v2_kb")
    facts = TurnFacts(
        router_lane="kb",
        effective_mode="complex",
        public_mode="complex",
        executor_profile="complex",
        pending_kind=PendingKind.NONE,
        primary_path_candidate=path,
        legacy_task_status="succeeded",
    )
    out = apply_turn_exit_to_chat_turn(
        {
            "ok": True,
            "answer": "x",
            "task_status": "succeeded",
            "primary_path": "stale_top_level",
            "extra": extra,
            "pipeline_ok": True,
        },
        facts=facts,
    )
    assert out["task_status"] == "succeeded"
    assert out["primary_path"] == "agno_basic_v2_kb"
    assert out["extra"]["primary_path"] == "agno_basic_v2_kb"
    assert out["extra"].get("pending_kind") is None
