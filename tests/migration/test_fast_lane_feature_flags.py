from __future__ import annotations

from threading import Lock
from types import SimpleNamespace

import pytest

from agents.main_agent.schema import AgnoCollaborationPlan, MainXiezuoPan
from agents.middle_agent.schema import AgnoMaterialBundle, CailiaoPan
from application.chat.history_buffer import ChatTurnDeps
from application.chat.run_chat_turn import run_agno_chat_turn_impl
from config import feature_flags
from schemas import MainDecision


def _legacy_deps() -> ChatTurnDeps:
    plan = AgnoCollaborationPlan(
        decision=MainDecision(task_id="p7-flag-off", task_status="routed"),
        force_skip_evidence=False,
        web_supplement_mode="explicit_only",
        answer_composition="default",
        xiezuo_pan=MainXiezuoPan(
            renwu_lei="waibu",
            zhengju_need=False,
            allow_kb=False,
            allow_web=True,
            fengxian_yinzi=0.5,
            celue_tag="complex",
        ),
        needs_retrieval=False,
        retrieval_strategy="none",
        answer_mode="direct",
        tools_allowed=(),
        max_rounds=1,
        original_user_intent="请总结这个视频",
    )
    bundle = AgnoMaterialBundle(
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
    return ChatTurnDeps(
        histories={},
        session_prev_video={},
        session_pending_video={},
        lock=Lock(),
        main_agent=SimpleNamespace(pan=lambda *a, **k: plan),
        middle_agent=SimpleNamespace(caipan=lambda *a, **k: bundle),
        answer_agent=SimpleNamespace(),
        run_basic_qa=lambda *a, **k: "complex-fallback",
        path_fingerprint=lambda *a, **k: "fp",
        nodes_contract=lambda trace: {},
    )


@pytest.mark.parametrize(
    ("flag", "message", "kwargs"),
    [
        ("ENABLE_FAST_LANE_VIDEO", "请总结这个视频 https://www.bilibili.com/video/BV1p7flag001", {}),
        ("ENABLE_FAST_LANE_WEB", "请阅读并总结这个网页 https://example.com/p7-flag", {}),
        (
            "ENABLE_FAST_LANE_DOCUMENT",
            "总结这个文档的核心内容",
            {"v13_text_content": "文档正文用于 P7 flag 测试。"},
        ),
        ("ENABLE_FAST_LANE_KB", "根据知识库说明数据库要求", {"use_knowledge": True}),
    ],
)
def test_lane_fast_flag_off_escalates_to_complex(
    monkeypatch: pytest.MonkeyPatch,
    flag: str,
    message: str,
    kwargs: dict[str, object],
) -> None:
    monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_INGRESS_ROUTER_V2", True)
    for lane_flag in feature_flags.LANE_FAST_FLAG.values():
        monkeypatch.setitem(feature_flags.FEATURE_FLAGS, lane_flag, True)
    monkeypatch.setitem(feature_flags.FEATURE_FLAGS, flag, False)
    monkeypatch.setattr(
        "application.chat.response_assembly.build_extra",
        lambda *a, **k: {"lane": "agno_basic", "primary_path": "agno_basic", "mode": "complex"},
    )
    out = run_agno_chat_turn_impl(message, session_id=f"p7-{flag}", deps=_legacy_deps(), **kwargs)
    extra = out["extra"]
    assert out["answer"] == "complex-fallback"
    assert "fast_lane_name" not in extra
    assert extra.get("fast_path") is not True
    assert str(out.get("primary_path") or "") not in {
        "direct_llm",
        "canned",
        "kb_fast",
        "web_fast",
    }


def test_general_fast_flag_off_skips_canned_shortcut(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_INGRESS_ROUTER_V2", True)
    for lane_flag in feature_flags.LANE_FAST_FLAG.values():
        monkeypatch.setitem(feature_flags.FEATURE_FLAGS, lane_flag, True)
    monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_FAST_LANE_GENERAL", False)
    monkeypatch.setattr(
        "application.chat.response_assembly.build_extra",
        lambda *a, **k: {"lane": "agno_basic", "primary_path": "agno_basic", "mode": "complex"},
    )
    out = run_agno_chat_turn_impl("你好", session_id="p7-general-off", deps=_legacy_deps())
    assert out["answer"] == "complex-fallback"
    assert "fast_lane_name" not in out["extra"]
