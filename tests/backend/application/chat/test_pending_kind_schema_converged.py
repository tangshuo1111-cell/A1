"""S10 — pending store canonical pending_kind (§9.3)."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from agents.main_agent.schema import AgnoCollaborationPlan, MainXiezuoPan
from application.chat.response_assembly import build_extra
from rag.pending_schema import (
    PENDING_KIND_COMMITTED,
    PENDING_KIND_MATERIAL_PENDING,
    PENDING_KIND_PROCESSING_PENDING,
    SOURCE_TYPE_WEB_URL,
    PendingKnowledgeItem,
    SourcePayload,
    derive_pending_kind,
)
from schemas import MainDecision
from services.capabilities.knowledge.pending_ingestion_service import commit_pending
from services.capabilities.knowledge.pending_service import resolve_pending_kind
from services.pending_store import create_default_pending_store, reset_pending_store_for_tests


@pytest.fixture(autouse=True)
def _reset_pending_store() -> None:
    reset_pending_store_for_tests()
    yield
    reset_pending_store_for_tests()


def test_derive_pending_kind_from_extract_status() -> None:
    assert (
        derive_pending_kind(extract_status="ok", commit_status="pending")
        == PENDING_KIND_MATERIAL_PENDING
    )
    assert (
        derive_pending_kind(extract_status="queued", commit_status="pending")
        == PENDING_KIND_PROCESSING_PENDING
    )
    assert (
        derive_pending_kind(extract_status="ok", commit_status="committed")
        == PENDING_KIND_COMMITTED
    )


def test_pending_item_create_sets_pending_kind() -> None:
    item = PendingKnowledgeItem.create(
        session_id="sess-pk",
        payload=SourcePayload(
            source_type=SOURCE_TYPE_WEB_URL,
            source_id="web:demo",
            title="Demo",
            text="body",
            metadata={"url": "https://example.com"},
            raw_source="https://example.com",
        ),
        parser_name="fetch_web",
        extract_status="ok",
    )
    assert item.pending_kind == PENDING_KIND_MATERIAL_PENDING
    assert resolve_pending_kind(item) == PENDING_KIND_MATERIAL_PENDING


def test_commit_pending_sets_committed_pending_kind(monkeypatch: pytest.MonkeyPatch) -> None:
    store = create_default_pending_store()
    item = PendingKnowledgeItem.create(
        session_id="sess-commit",
        payload=SourcePayload(
            source_type=SOURCE_TYPE_WEB_URL,
            source_id="web:commit",
            title="Commit me",
            text="content to ingest",
            metadata={"source_id": "web:commit"},
            raw_source="https://example.com/doc",
        ),
        parser_name="fetch_web",
        extract_status="ok",
    )
    store.add(item)

    monkeypatch.setattr(
        "storage.knowledge_store.save_document_text",
        lambda *_a, **_k: 3,
    )
    result = commit_pending(item.pending_id, store=store)
    assert result.success is True
    committed = store.get(item.pending_id)
    assert committed is not None
    assert committed.pending_kind == PENDING_KIND_COMMITTED
    assert resolve_pending_kind(committed) == PENDING_KIND_COMMITTED


def test_build_extra_reads_store_pending_kind() -> None:
    pending_item = PendingKnowledgeItem.create(
        session_id="sess-extra",
        payload=SourcePayload(
            source_type=SOURCE_TYPE_WEB_URL,
            source_id="web:extra",
            title="Pending page",
            text="preview",
            metadata={"source_id": "web:extra"},
            raw_source="https://example.com/p",
        ),
        parser_name="fetch_web",
        extract_status="queued",
    )

    from agents.middle_agent.schema import AgnoMaterialBundle, CailiaoPan

    bundle = AgnoMaterialBundle(
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
            laiyuan_zhu="web",
            use_kb=False,
            use_web=True,
            que_shenme="none",
            xia_yi_bu="zhi_da",
        ),
        pending_item=pending_item,
    )
    plan = AgnoCollaborationPlan(
        decision=MainDecision(task_id="s10", task_status="routed"),
        force_skip_evidence=False,
        web_supplement_mode="explicit_only",
        answer_composition="default",
        xiezuo_pan=MainXiezuoPan(
            renwu_lei="waibu",
            zhengju_need=True,
            allow_kb=False,
            allow_web=True,
            fengxian_yinzi=0.5,
            celue_tag="complex",
        ),
    )
    history = SimpleNamespace(
        session_id="sess-extra",
        turns=0,
        has_prev_video=False,
        prev_video=None,
        pending_video_text=None,
    )
    extra = build_extra(
        "总结网页",
        plan,
        bundle,
        plan.decision,
        "answer",
        SimpleNamespace(
            answer_agent=SimpleNamespace(
                pan=lambda *_a, **_k: SimpleNamespace(lane="web", primary_path="complex"),
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

    assert extra.get(EXIT_SIGNAL_PENDING_KIND) == PENDING_KIND_PROCESSING_PENDING
    assert "pending_kind" not in extra
    assert extra["pending_source_id"] == pending_item.pending_id
    assert "v13_pending" not in extra


def test_build_extra_primary_path_comes_from_bundle_material_not_answer_label() -> None:
    from agents.middle_agent.schema import AgnoMaterialBundle, CailiaoPan

    bundle = AgnoMaterialBundle(
        knowledge_block="KB material",
        web_block=None,
        trace=[],
        knowledge_adequate=True,
        material_still_insufficient=False,
        web_judgment_reason="explicit_only",
        kb_evidence_tier="strong",
        insufficiency_signal="ok",
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
        decision=MainDecision(task_id="s10-path", task_status="routed"),
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
        session_id="sess-path",
        turns=0,
        has_prev_video=False,
        prev_video=None,
        pending_video_text=None,
    )
    extra = build_extra(
        "根据知识回答",
        plan,
        bundle,
        plan.decision,
        "answer",
        SimpleNamespace(
            answer_agent=SimpleNamespace(
                pan=lambda *_a, **_k: SimpleNamespace(lane="general", primary_path="wrong_answer_label"),
                xiezuo_extra=lambda *_a, **_k: {},
            ),
            path_fingerprint=lambda *_a, **_k: "fp",
            nodes_contract=lambda *_a, **_k: {},
        ),
        use_knowledge=True,
        knowledge_block="KB material",
        web_block=None,
        collab_trace=[],
        history_snapshot=history,
    )
    assert extra["lane"] == "agno_basic_v2_kb"
    from application.chat.exit_signals import EXIT_SIGNAL_PRIMARY_PATH

    assert extra.get(EXIT_SIGNAL_PRIMARY_PATH) == "agno_basic_v2_kb"
    assert extra.get("primary_path") is None
