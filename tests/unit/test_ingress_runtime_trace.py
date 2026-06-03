from __future__ import annotations

from threading import Lock
from types import SimpleNamespace

import pytest

from agents.main_agent.schema import AgnoCollaborationPlan, MainXiezuoPan
from agents.middle_agent.schema import AgnoMaterialBundle, CailiaoPan
from application.chat.history_buffer import ChatTurnDeps
from application.chat.run_chat_turn import run_agno_chat_turn_impl
from schemas import MainDecision


def _plan() -> AgnoCollaborationPlan:
    return AgnoCollaborationPlan(
        decision=MainDecision(task_id="p6-task", task_status="routed"),
        force_skip_evidence=False,
        web_supplement_mode="explicit_only",
        answer_composition="default",
        xiezuo_pan=MainXiezuoPan(
            renwu_lei="zhishu",
            zhengju_need=True,
            allow_kb=False,
            allow_web=True,
            fengxian_yinzi=0.3,
            celue_tag="general",
        ),
    )


def _bundle() -> AgnoMaterialBundle:
    return AgnoMaterialBundle(
        knowledge_block=None,
        web_block=None,
        trace=[],
        knowledge_adequate=False,
        material_still_insufficient=False,
        web_judgment_reason="skip",
        kb_evidence_tier="none",
        insufficiency_signal="none",
        cailiao_pan=CailiaoPan(
            gou=True,
            kb_qiangdu=0.0,
            bukong_xinhao="ok",
            laiyuan_zhu="wu",
            use_kb=False,
            use_web=False,
            que_shenme="none",
            xia_yi_bu="zhi_da",
        ),
    )


def _deps(plan: AgnoCollaborationPlan, bundle: AgnoMaterialBundle) -> ChatTurnDeps:
    return ChatTurnDeps(
        histories={},
        session_prev_video={},
        session_pending_video={},
        lock=Lock(),
        main_agent=SimpleNamespace(pan=lambda *a, **k: plan),
        middle_agent=SimpleNamespace(caipan=lambda *a, **k: bundle),
        answer_agent=SimpleNamespace(),
        run_basic_qa=lambda *a, **k: "stub-answer",
        path_fingerprint=lambda *a, **k: "fp",
        nodes_contract=lambda trace: {},
    )


@pytest.mark.parametrize(
    ("message", "use_knowledge", "v13_file_content", "expected_lane"),
    [
        ("请总结这个视频 https://www.bilibili.com/video/BV1xx411c7mD", False, None, "video"),
        ("请阅读并总结这个网页 https://example.com/article", False, None, "web"),
        ("根据知识库说明一下当前系统的数据库要求", True, None, "kb"),
        ("总结这个文档的核心内容", False, b"doc-bytes", "document"),
    ],
)
def test_run_chat_turn_emits_ingress_router_trace(
    monkeypatch: pytest.MonkeyPatch,
    message: str,
    use_knowledge: bool,
    v13_file_content: bytes | None,
    expected_lane: str,
) -> None:
    monkeypatch.setattr(
        "application.chat.run_chat_turn._build_extra",
        lambda *a, **k: {"lane": "agno_basic", "primary_path": "agno_basic"},
    )
    # 视频快路径会真实抓取（yt_dlp）；本用例只验证路由 trace，stub 掉以免触网（CI 无外网）。
    monkeypatch.setattr(
        "tools.video.extract_web_video_subtitle._extract_web_video_subtitle",
        lambda url, session_id="": SimpleNamespace(
            status="success",
            text="字幕文本，用于路由 trace 测试。",
            title="测试视频",
            metadata={"duration": 5.0, "transcript_source": "subtitle"},
            transcript_source="subtitle",
            error_code="",
            failure_reason="",
        ),
    )
    out = run_agno_chat_turn_impl(
        message,
        session_id="p6-runtime",
        use_knowledge=use_knowledge,
        v13_file_content=v13_file_content,
        deps=_deps(_plan(), _bundle()),
    )
    extra = out["extra"]
    assert extra["router_lane"] == expected_lane
    assert extra["mode"] in {"fast", "complex", "async"}
    assert extra["router_source"] in {"rule", "light_classifier", "main_agent"}
    assert 0.0 <= float(extra["router_confidence"]) <= 1.0
