from __future__ import annotations

import csv
from pathlib import Path
from threading import Lock
from types import SimpleNamespace

import pytest
from tests._support.capability_probe_fixtures import web_probe_sync_ok

from agents.answer_agent import AnswerAgent
from agents.main_agent.schema import AgnoCollaborationPlan, MainXiezuoPan
from agents.middle_agent.schema import AgnoMaterialBundle, CailiaoPan
from application.chat.history_buffer import ChatTurnDeps
from application.chat.run_chat_turn import run_agno_chat_turn_impl
from application.ingress.lane_decision_schema import LaneDecision
from config import feature_flags
from schemas import MainDecision

ROUTE_TABLE = Path("docs/current/migration/route_target_table.csv")
LEGACY_STATUS = Path("docs/current/migration/legacy_paths_status.csv")
BASELINE_SAMPLES = Path("docs/current/baselines/samples")


def _load_route_rows() -> list[dict[str, str]]:
    with ROUTE_TABLE.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _baseline_sample_ids() -> set[str]:
    ids: set[str] = set()
    for path in BASELINE_SAMPLES.glob("*.yaml"):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("sample_id:"):
                ids.add(line.split(":", 1)[1].strip())
                break
    return ids


def test_p10_new_architecture_flags_default_on() -> None:
    assert feature_flags.is_enabled("ENABLE_INGRESS_ROUTER_V2") is True
    assert feature_flags.is_enabled("ENABLE_THREE_AGENT_AUTONOMY") is True
    assert feature_flags.is_enabled("ENABLE_ASYNC_CONTROL_PLANE_V2") is True
    for lane_flag in feature_flags.LANE_FAST_FLAG.values():
        assert feature_flags.is_enabled(lane_flag) is True


def test_p10_route_target_table_covers_all_baseline_samples() -> None:
    sample_ids = _baseline_sample_ids()
    route_ids = {row["sample_id"] for row in _load_route_rows()}
    assert len(sample_ids) >= 7
    assert sample_ids <= route_ids


def test_p10_legacy_paths_are_retired() -> None:
    with LEGACY_STATUS.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows
    assert all(str(row["status"]).strip() == "retired" for row in rows)


def _simple_complex_deps() -> ChatTurnDeps:
    plan = AgnoCollaborationPlan(
        decision=MainDecision(task_id="p10-doc-complex", task_status="routed"),
        force_skip_evidence=False,
        web_supplement_mode="explicit_only",
        answer_composition="default",
        xiezuo_pan=MainXiezuoPan(
            renwu_lei="wenjian",
            zhengju_need=True,
            allow_kb=False,
            allow_web=False,
            fengxian_yinzi=0.7,
            celue_tag="document_ocr",
        ),
        needs_retrieval=False,
        retrieval_strategy="none",
        answer_mode="direct",
        tools_allowed=(),
        max_rounds=1,
        original_user_intent="请提取这个扫描版 PDF 的重点并按章节整理",
    )
    bundle = AgnoMaterialBundle(
        knowledge_block="",
        web_block="",
        trace=["v16:document:ocr_complex"],
        knowledge_adequate=False,
        material_still_insufficient=True,
        web_judgment_reason="skip",
        kb_evidence_tier="none",
        insufficiency_signal="need_ocr",
        cailiao_pan=CailiaoPan(
            gou=False,
            kb_qiangdu=0.0,
            bukong_xinhao="que",
            laiyuan_zhu="document",
            use_kb=False,
            use_web=False,
            que_shenme="ocr",
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
        answer_agent=AnswerAgent(),
        run_basic_qa=lambda *a, **k: "大文档 OCR 复杂链回答",
        path_fingerprint=lambda *a, **k: "fp",
        nodes_contract=lambda trace: {},
    )


def test_web_read_request_stays_in_web_fast_lane(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "services.capabilities.web.web_orchestration_service.probe_web_capability",
        lambda url, clock=None: web_probe_sync_ok(url),
    )
    monkeypatch.setattr(
        "services.capabilities.web.web_orchestration_service.fetch_web_evidence_block",
        lambda *_a, **_k: "[Web检索] Phase 10 网页快链材料",
    )
    out = run_agno_chat_turn_impl(
        "请阅读并总结这个网页 https://example.com/phase10-web",
        session_id="p10-web",
        deps=ChatTurnDeps(
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
        ),
    )
    extra = out["extra"]
    assert extra["router_lane"] == "web"
    assert extra["mode"] == "fast"
    assert extra["fast_lane_name"] == "web"
    assert "loop_id" not in extra


def test_kb_query_stays_in_kb_fast_lane(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "application.chat.run_chat_turn.resolve_lane_decision",
        lambda **_k: LaneDecision(
            lane="kb",
            mode="fast",
            router_source="rule",
            router_confidence=0.95,
            router_decision_ms=0,
        ),
    )
    monkeypatch.setattr(
        "application.chat.run_chat_turn._run_kb_fast_path",
        lambda **_k: (
            "系统默认数据库要求 PostgreSQL。",
            {
                "fast_path": "kb_fast",
                "lane": "kb",
                "mode": "fast",
                "executor_profile": "fast",
                "fast_lane_name": "kb",
                "capabilities_called": ["capability.kb.retrieve"],
                "fast_exit_reason": "kb_retrieve_answer",
            },
        ),
    )
    monkeypatch.setattr(
        "application.chat.run_chat_turn._finalize_fast_path_delivery",
        lambda **kwargs: (True, "fast", kwargs["lane_extra"]),
    )
    out = run_agno_chat_turn_impl(
        "根据知识库说明一下当前系统的数据库要求",
        session_id="p10-kb",
        use_knowledge=True,
        deps=ChatTurnDeps(
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
        ),
    )
    extra = out["extra"]
    assert extra["router_lane"] == "kb"
    assert extra["mode"] == "fast"
    assert extra["fast_lane_name"] == "kb"
    assert "capability.kb.retrieve" in extra["capabilities_called"]
    assert "loop_id" not in extra


def test_large_document_ocr_enters_complex_document_lane(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_THREE_AGENT_AUTONOMY", False)
    out = run_agno_chat_turn_impl(
        "请提取这个扫描版 PDF 的重点并按章节整理",
        session_id="p10-large-doc",
        v13_file_content=b"fixture-pdf",
        deps=_simple_complex_deps(),
    )
    extra = out["extra"]
    assert extra["router_lane"] == "document"
    assert extra["mode"] == "complex"
    assert "fast_lane_name" not in extra
    assert "loop_id" not in extra


def test_long_video_async_lane_returns_pending_task(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "services.execution.task_plane_service.enqueue_video_background_task",
        lambda **kwargs: ("task-video-async", "memory"),
    )
    out = run_agno_chat_turn_impl(
        "帮我总结这个长视频的重点 https://www.youtube.com/watch?v=phase10long001",
        session_id="p10-long-video",
        confirm_long_web_video_asr=True,
        deps=_simple_complex_deps(),
    )
    extra = out["extra"]
    assert extra["router_lane"] == "video"
    assert extra["mode"] == "async"
    assert out["task_id"] == "task-video-async"
    assert out["task_status"] == "pending"
