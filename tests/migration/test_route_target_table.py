from __future__ import annotations

import csv
from pathlib import Path
from threading import Lock
from types import SimpleNamespace

import pytest

from agents.main_agent.schema import AgnoCollaborationPlan, MainXiezuoPan
from agents.middle_agent.schema import AgnoMaterialBundle, CailiaoPan
from application.chat.budget_clock import BudgetClock
from application.chat.history_buffer import ChatTurnDeps
from application.chat.run_chat_turn import run_agno_chat_turn_impl
from application.ingress import route_chat_request
from schemas import MainDecision

TABLE_PATH = Path("docs/current/migration/route_target_table.csv")


def _deps() -> ChatTurnDeps:
    return ChatTurnDeps(
        histories={},
        session_prev_video={},
        session_pending_video={},
        lock=Lock(),
        main_agent=SimpleNamespace(pan=lambda *a, **k: None),
        middle_agent=SimpleNamespace(caipan=lambda *a, **k: None),
        answer_agent=SimpleNamespace(),
        run_basic_qa=lambda *a, **k: "unused",
        path_fingerprint=lambda *a, **k: "fp",
        nodes_contract=lambda trace: {},
    )


def _complex_deps() -> ChatTurnDeps:
    plan = AgnoCollaborationPlan(
        decision=MainDecision(task_id="p10-complex", task_status="routed"),
        force_skip_evidence=False,
        web_supplement_mode="explicit_only",
        answer_composition="default",
        xiezuo_pan=MainXiezuoPan(
            renwu_lei="waibu",
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
        original_user_intent="结合知识库、网页和文档给出建议",
        budget_policy={"llm_calls_remaining": 2, "tool_calls_remaining": 2},
    )
    bundle = AgnoMaterialBundle(
        knowledge_block="知识库资料：方案 A 成本低。",
        web_block="[Web检索] 网页资料：方案 B 落地更快。",
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
    return ChatTurnDeps(
        histories={},
        session_prev_video={},
        session_pending_video={},
        lock=Lock(),
        main_agent=SimpleNamespace(pan=lambda *a, **k: plan),
        middle_agent=SimpleNamespace(caipan=lambda *a, **k: bundle),
        answer_agent=SimpleNamespace(
            pan=lambda *_a, **_k: SimpleNamespace(lane="general", primary_path="complex_autonomy"),
            xiezuo_extra=lambda *_a, **_k: {},
            review_multisource=lambda *_a, **_k: {
                "feedback_request": {
                    "request_type": "more_web_material",
                    "reason": "需要更多证据后再签字",
                }
            },
        ),
        run_basic_qa=lambda *a, **k: "综合知识库、网页和文档后，建议优先方案 B。",
        path_fingerprint=lambda *a, **k: "fp",
        nodes_contract=lambda trace: {},
    )


def _load_rows() -> list[dict[str, str]]:
    with TABLE_PATH.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


@pytest.mark.parametrize("row", _load_rows(), ids=lambda row: row["sample_id"])
def test_route_target_table_matches_ingress_contract(row: dict[str, str]) -> None:
    message_by_sample = {
        "video_url_summary_001": "请总结这个视频 https://www.bilibili.com/video/BV1phase1001",
        "video_url_summary_002": "帮我总结这个长视频的重点 https://www.youtube.com/watch?v=phase10long001",
        "local_video_summary_001": "请总结我刚上传的视频内容",
        "small_doc_summary_001": "总结这个文档的核心内容",
        "large_doc_ocr_001": "请提取这个扫描版 PDF 的重点并按章节整理",
        "web_read_001": "请阅读并总结这个网页 https://example.com/phase10-web",
        "kb_query_simple_001": "根据知识库说明一下当前系统的数据库要求",
        "multi_source_complex_001": "结合知识库、网页和我上传的文档，比较这三个方案的优缺点并给出建议",
    }
    attachments_by_sample = {
        "local_video_summary_001": [{"type": "local_file", "name": "sample_local_video.mp4"}],
        "small_doc_summary_001": [{"type": "local_file", "name": "sample_small_doc.pdf"}],
        "large_doc_ocr_001": [{"type": "local_file", "name": "sample_scanned_doc.pdf"}],
        "multi_source_complex_001": [{"type": "local_file", "name": "decision_options.docx"}],
    }
    use_knowledge = row["sample_id"] in {"kb_query_simple_001", "multi_source_complex_001"}
    attachments = attachments_by_sample.get(row["sample_id"], [])
    decision = route_chat_request(
        message=message_by_sample[row["sample_id"]],
        session_id=f"p10-{row['sample_id']}",
        request_id=f"p10-{row['sample_id']}",
        use_knowledge=use_knowledge,
        v13_file_content=b"fixture" if attachments else None,
        v13_text_content=None,
        attachments=attachments,
        clock=BudgetClock.start(),
    )
    assert decision.lane == row["lane"]
    assert decision.mode == row["mode"]


def test_video_request_does_not_default_to_kb_or_web_heavy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "tools.video.extract_web_video_subtitle._extract_web_video_subtitle",
        lambda *_a, **_k: SimpleNamespace(
            status="success",
            text="视频内容围绕 Phase 10 路由验收。",
            title="p10-video",
            transcript_source="subtitle",
            metadata={"text_source": "subtitle"},
        ),
    )
    out = run_agno_chat_turn_impl(
        "请总结这个视频 https://www.bilibili.com/video/BV1phase1002",
        session_id="p10-video",
        deps=_deps(),
    )
    extra = out["extra"]
    assert extra["fast_lane_name"] == "video"
    assert "capability.video.subtitle_probe" in extra["capabilities_called"]
    assert "capability.kb.retrieve" not in extra["capabilities_called"]


def test_simple_document_request_stays_in_document_fast_lane() -> None:
    out = run_agno_chat_turn_impl(
        "总结这个文档的核心内容",
        session_id="p10-doc",
        v13_text_content="这是一个小文档，主要介绍 Phase 10 的验收目标。",
        deps=_deps(),
    )
    extra = out["extra"]
    assert extra["lane"] == "document"
    assert extra["mode"] == "fast"
    assert extra["fast_lane_name"] == "document"
    assert "loop_id" not in extra


def test_multisource_request_enters_complex_autonomy_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "application.chat.complex_path_entry.agno_web_service.fetch_web_evidence_block",
        lambda *_a, **_k: "[Web检索] 方案 B 具备更好的上线节奏。",
    )
    out = run_agno_chat_turn_impl(
        "结合知识库、网页和我上传的文档，比较这三个方案的优缺点并给出建议",
        session_id="p10-complex",
        use_knowledge=True,
        v13_file_content=b"fixture",
        deps=_complex_deps(),
    )
    extra = out["extra"]
    assert extra["mode"] == "complex"
    assert str(extra["loop_id"]).startswith("loop_")
    assert isinstance(extra["autonomy_events"], list) and extra["autonomy_events"]
