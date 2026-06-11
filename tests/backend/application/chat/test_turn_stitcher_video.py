"""S8 — inter-turn stitch from completed async video task (§6.6)."""
from __future__ import annotations

from threading import Lock
from types import SimpleNamespace

import pytest

from agents.main_agent.schema import AgnoCollaborationPlan, MainXiezuoPan
from agents.middle_agent.schema import AgnoMaterialBundle, CailiaoPan
from application.chat.history_buffer import ChatTurnDeps
from application.chat.run_chat_turn import run_agno_chat_turn_impl
from application.ingress.lane_decision_schema import LaneDecision
from config import feature_flags
from schemas import MainDecision
from tasks.orchestration.turn_stitcher import (
    maybe_attach_task_result,
    peek_stitch_slot,
    reset_stitch_slots_for_tests,
)


@pytest.fixture(autouse=True)
def _clear_stitch_slots() -> None:
    reset_stitch_slots_for_tests()
    yield
    reset_stitch_slots_for_tests()


def test_turn_stitcher_video_continues_without_reprobe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_TURN_STITCHER", True)
    monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_ASYNC_CONTROL_PLANE_V2", True)
    monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_INGRESS_ROUTER_V2", True)
    monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_FAST_LANE_VIDEO", True)
    monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_FAST_LANE_GATE", True)

    probe_calls = {"n": 0}

    def _probe(*_args, **_kwargs):
        probe_calls["n"] += 1
        raise AssertionError("video subtitle probe must not run after stitch")

    monkeypatch.setattr(
        "tools.video.extract_web_video_subtitle._extract_web_video_subtitle",
        _probe,
    )
    monkeypatch.setattr(
        "application.ingress.resolve_lane_decision",
        lambda **_kwargs: LaneDecision(
            lane="video",
            mode="fast",
            router_source="rule",
            router_confidence=0.95,
            router_decision_ms=2,
        ),
    )
    monkeypatch.setattr(
        "application.chat.response_assembly.build_extra",
        lambda *_a, **_k: {"lane": "video", "primary_path": "complex"},
    )
    monkeypatch.setattr(
        "application.chat.executors.fast_executor_general.can_use_direct_fast_path",
        lambda *_a, **_k: False,
    )

    task_rows = {
        "task-vid-001": {
            "task_id": "task-vid-001",
            "session_id": "sess-stitch",
            "metadata": {},
        }
    }

    def _get_job(task_id: str):
        return task_rows.get(task_id)

    def _update_task_async_metadata(task_id: str, *, metadata: dict):
        row = task_rows.get(task_id)
        if row is None:
            return
        current = dict(row.get("metadata") or {})
        current.update(metadata or {})
        row["metadata"] = current

    def _list_recent_jobs(limit: int = 200):
        return list(task_rows.values())[:limit]

    monkeypatch.setattr(
        "tasks.orchestration.turn_stitcher.task_job_store.get_job",
        _get_job,
    )
    monkeypatch.setattr(
        "tasks.orchestration.turn_stitcher.task_job_store.update_task_async_metadata",
        _update_task_async_metadata,
    )
    monkeypatch.setattr(
        "tasks.orchestration.turn_stitcher.task_job_store.list_recent_jobs",
        _list_recent_jobs,
    )

    maybe_attach_task_result(
        session_id="sess-stitch",
        task_id="task-vid-001",
        result_summary={"final_answer": "视频讲的是量子计算基础原理。"},
        lane="video",
    )
    assert peek_stitch_slot("sess-stitch") is not None

    deps = ChatTurnDeps(
        histories={},
        session_prev_video={},
        session_pending_video={},
        lock=Lock(),
        main_agent=SimpleNamespace(
            pan=lambda *a, **k: AgnoCollaborationPlan(
                decision=MainDecision(task_id="s8-stitch", task_status="routed"),
                force_skip_evidence=False,
                web_supplement_mode="explicit_only",
                answer_composition="default",
                xiezuo_pan=MainXiezuoPan(
                    renwu_lei="waibu",
                    zhengju_need=True,
                    allow_kb=False,
                    allow_web=False,
                    fengxian_yinzi=0.5,
                    celue_tag="complex",
                ),
            )
        ),
        middle_agent=SimpleNamespace(
            caipan=lambda *a, **k: AgnoMaterialBundle(
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
                    laiyuan_zhu="video",
                    use_kb=False,
                    use_web=False,
                    que_shenme="none",
                    xia_yi_bu="zhi_da",
                ),
            )
        ),
        answer_agent=SimpleNamespace(),
        run_basic_qa=lambda *a, **k: "基于后台字幕的接续回答",
        path_fingerprint=lambda *a, **k: "fp",
        nodes_contract=lambda trace: {},
    )

    out = run_agno_chat_turn_impl("它讲了什么", session_id="sess-stitch", deps=deps)

    assert probe_calls["n"] == 0
    assert out["extra"].get("turn_stitch.applied") is True
    assert out["answer"] == "基于后台字幕的接续回答"
    assert peek_stitch_slot("sess-stitch") is None
    pending = deps.session_pending_video.get("sess-stitch")
    assert pending is not None
    assert "量子计算" in (pending.text or "")
