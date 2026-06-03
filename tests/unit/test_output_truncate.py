"""application.chat.run_chat_turn：Stage 6 输出长度按 COST.max_output_chars 截断。"""

from __future__ import annotations

import importlib
import sys
from threading import Lock
from unittest.mock import MagicMock

import pytest
from tests._support.bootstrap import find_repo_root

REPO_ROOT = find_repo_root(__file__)
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _reload_cost_rule() -> None:
    import config.cost_rule as cr

    importlib.reload(cr)


def disable_fast_lane_shortcuts(monkeypatch: pytest.MonkeyPatch) -> None:
    from config import feature_flags

    for flag in feature_flags.LANE_FAST_FLAG.values():
        monkeypatch.setitem(feature_flags.FEATURE_FLAGS, flag, False)


def _enable_legacy_turn(monkeypatch: pytest.MonkeyPatch) -> None:
    disable_fast_lane_shortcuts(monkeypatch)
    monkeypatch.setattr(
        "application.chat.run_chat_turn._run_feedback_round_execution",
        lambda message, plan, bundle, deps, **kwargs: bundle,
    )


@pytest.fixture(autouse=True)
def _restore_output_chars(monkeypatch: pytest.MonkeyPatch) -> None:
    yield
    monkeypatch.delenv("MAX_OUTPUT_CHARS", raising=False)
    _reload_cost_rule()


def test_run_agno_chat_turn_impl_truncates_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_legacy_turn(monkeypatch)
    monkeypatch.setenv("MAX_OUTPUT_CHARS", "80")
    _reload_cost_rule()
    monkeypatch.setattr(
        "application.chat.run_chat_turn._build_extra",
        lambda *a, **k: {"lane": "direct", "primary_path": "test"},
    )

    from application.chat.run_chat_turn import ChatTurnDeps, run_agno_chat_turn_impl

    long_answer = "汉" * 200
    plan = MagicMock()
    plan.decision = MagicMock()
    plan.decision.task_id = "out-t1"
    plan.job_type = ""
    plan.web_supplement_mode = ""
    plan.answer_composition = ""
    plan.force_skip_evidence = False
    plan.needs_retrieval = False
    plan.retrieval_strategy = "auto"
    plan.needs_pending = False
    plan.pending_reference = "none"
    plan.answer_mode = "direct"
    plan.tools_allowed = ()
    main = MagicMock()
    main.pan.return_value = plan

    bundle = MagicMock()
    bundle.knowledge_block = ""
    bundle.web_block = ""
    bundle.trace = []
    bundle.pending_item = None
    bundle.v11_pending_video_text = None
    bundle.v11_saved_to_kb = False
    bundle.v11_saved_source_id = ""
    bundle.v11_saved_title = ""
    bundle.web_judgment_reason = ""
    bundle.material_still_insufficient = False
    bundle.kb_evidence_tier = ""
    bundle.insufficiency_signal = ""
    bundle.retrieved_chunks = []
    bundle.temporary_materials = []
    bundle.bundle_id = "b1"
    bundle.material_sufficiency = "sufficient"
    bundle.execution_status = "ok"
    bundle.failures = []
    middle = MagicMock()
    middle.caipan.return_value = bundle

    deps = ChatTurnDeps(
        histories={},
        session_prev_video={},
        session_pending_video={},
        lock=Lock(),
        main_agent=main,
        middle_agent=middle,
        answer_agent=MagicMock(),
        run_basic_qa=lambda *a, **k: long_answer,
        path_fingerprint=lambda *a, **k: "fp",
        nodes_contract=lambda tr: {},
    )

    out = run_agno_chat_turn_impl("请根据知识库资料详细回答这个问题", session_id="s trunc", deps=deps)
    assert len(out["answer"]) == 80


def test_truncation_disabled_when_under_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_legacy_turn(monkeypatch)
    monkeypatch.setenv("MAX_OUTPUT_CHARS", "5000")
    _reload_cost_rule()
    monkeypatch.setattr(
        "application.chat.run_chat_turn._build_extra",
        lambda *a, **k: {"lane": "direct", "primary_path": "test"},
    )
    from application.chat.run_chat_turn import ChatTurnDeps, run_agno_chat_turn_impl

    txt = "short"
    plan = MagicMock()
    plan.decision = MagicMock()
    plan.decision.task_id = "out-t2"
    plan.job_type = ""
    for attr, val in [
        ("web_supplement_mode", ""),
        ("answer_composition", ""),
        ("force_skip_evidence", False),
        ("needs_retrieval", False),
        ("retrieval_strategy", "auto"),
        ("needs_pending", False),
        ("pending_reference", "none"),
        ("answer_mode", "direct"),
        ("tools_allowed", ()),
    ]:
        setattr(plan, attr, val)
    main = MagicMock()
    main.pan.return_value = plan
    bundle = MagicMock()
    bundle.knowledge_block = ""
    bundle.web_block = ""
    bundle.trace = []
    bundle.pending_item = None
    bundle.v11_pending_video_text = None
    bundle.v11_saved_to_kb = False
    bundle.v11_saved_source_id = ""
    bundle.v11_saved_title = ""
    bundle.web_judgment_reason = ""
    bundle.material_still_insufficient = False
    bundle.kb_evidence_tier = ""
    bundle.insufficiency_signal = ""
    bundle.retrieved_chunks = []
    bundle.temporary_materials = []
    bundle.bundle_id = "b2"
    bundle.material_sufficiency = "sufficient"
    bundle.execution_status = "ok"
    bundle.failures = []
    middle = MagicMock()
    middle.caipan.return_value = bundle
    deps = ChatTurnDeps(
        histories={},
        session_prev_video={},
        session_pending_video={},
        lock=Lock(),
        main_agent=main,
        middle_agent=middle,
        answer_agent=MagicMock(),
        run_basic_qa=lambda *a, **k: txt,
        path_fingerprint=lambda *a, **k: "fp",
        nodes_contract=lambda tr: {},
    )
    out = run_agno_chat_turn_impl("请根据知识库资料详细回答这个问题", session_id="s2", deps=deps)
    assert out["answer"] == txt


def test_run_agno_chat_turn_impl_exposes_sla_budget_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_legacy_turn(monkeypatch)
    monkeypatch.setattr(
        "application.chat.run_chat_turn._build_extra",
        lambda *a, **k: {"lane": "direct", "primary_path": "test"},
    )
    from agents.main_agent.schema import AgnoCollaborationPlan, MainXiezuoPan
    from application.chat.run_chat_turn import ChatTurnDeps, run_agno_chat_turn_impl
    from schemas import MainDecision

    plan = AgnoCollaborationPlan(
        decision=MainDecision(
            task_id="budget-t1",
            task_status="routed",
        ),
        force_skip_evidence=False,
        web_supplement_mode="",
        answer_composition="",
        xiezuo_pan=MainXiezuoPan(
            renwu_lei="zhijie",
            zhengju_need=False,
            allow_kb=False,
            allow_web=False,
            fengxian_yinzi=0.0,
            celue_tag="direct",
        ),
        needs_retrieval=False,
        retrieval_strategy="auto",
        needs_pending=False,
        pending_reference="none",
        answer_mode="direct",
        tools_allowed=(),
    )
    main = MagicMock()
    main.pan.return_value = plan

    seen_plans: list[object] = []

    bundle = MagicMock()
    bundle.knowledge_block = ""
    bundle.web_block = ""
    bundle.trace = []
    bundle.pending_item = None
    bundle.v11_pending_video_text = None
    bundle.v11_saved_to_kb = False
    bundle.v11_saved_source_id = ""
    bundle.v11_saved_title = ""
    bundle.web_judgment_reason = ""
    bundle.material_still_insufficient = False
    bundle.kb_evidence_tier = ""
    bundle.insufficiency_signal = ""
    bundle.retrieved_chunks = []
    bundle.temporary_materials = []
    bundle.bundle_id = "budget-b1"
    bundle.material_sufficiency = "sufficient"
    bundle.execution_status = "ok"
    bundle.failures = []

    def _capture_middle(*args: object, **kwargs: object) -> object:
        seen_plans.append(kwargs["plan"])
        return bundle

    middle = MagicMock()
    middle.caipan.side_effect = _capture_middle

    deps = ChatTurnDeps(
        histories={},
        session_prev_video={},
        session_pending_video={},
        lock=Lock(),
        main_agent=main,
        middle_agent=middle,
        answer_agent=MagicMock(),
        run_basic_qa=lambda *a, **k: "ok",
        path_fingerprint=lambda *a, **k: "fp",
        nodes_contract=lambda tr: {},
    )

    out = run_agno_chat_turn_impl("请根据知识库资料详细回答这个问题", session_id="s-budget", deps=deps)

    extra = out["extra"]
    assert extra["sla_deadline_ms"] == 30000
    assert isinstance(extra["elapsed_ms"], int)
    assert isinstance(extra["remaining_ms_at_answer_start"], int)
    assert extra["progress_stage"] == "completed"
    assert isinstance(extra["agent_timings"], dict)
    assert extra["agent_timings"]["total_ms"] == extra["elapsed_ms"]
    assert seen_plans, "middle.caipan 应收到带预算信息的 plan"
    mid_plan = seen_plans[0]
    assert getattr(mid_plan, "sla_budget_ms", 0) == 30000
    assert getattr(mid_plan, "main_elapsed_ms", -1) >= 0


def test_run_agno_chat_turn_impl_fast_path_exposes_sla_budget_fields() -> None:
    from application.chat.run_chat_turn import ChatTurnDeps, run_agno_chat_turn_impl

    deps = ChatTurnDeps(
        histories={},
        session_prev_video={},
        session_pending_video={},
        lock=Lock(),
        main_agent=MagicMock(),
        middle_agent=MagicMock(),
        answer_agent=MagicMock(),
        run_basic_qa=lambda *a, **k: "unused",
        path_fingerprint=lambda *a, **k: "fp",
        nodes_contract=lambda tr: {},
    )

    out = run_agno_chat_turn_impl("你好", session_id="s-fast-budget", deps=deps)
    extra = out["extra"]
    assert extra["sla_deadline_ms"] == 30000
    assert isinstance(extra["elapsed_ms"], int)
    assert extra["progress_stage"] == "completed"
    assert isinstance(extra["agent_timings"], dict)


def test_run_agno_chat_turn_impl_short_circuits_when_deadline_exhausted(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_legacy_turn(monkeypatch)
    monkeypatch.setattr("application.chat.run_chat_turn.SLA_BUDGET_MS", 20000)
    monkeypatch.setattr(
        "application.chat.run_chat_turn._build_extra",
        lambda *a, **k: {"lane": "default", "primary_path": "deadline-test"},
    )
    from agents.main_agent.schema import AgnoCollaborationPlan, MainXiezuoPan
    from application.chat.run_chat_turn import ChatTurnDeps, run_agno_chat_turn_impl
    from schemas import MainDecision

    plan = AgnoCollaborationPlan(
        decision=MainDecision(task_id="deadline-t1", task_status="routed"),
        force_skip_evidence=False,
        web_supplement_mode="",
        answer_composition="",
        xiezuo_pan=MainXiezuoPan(
            renwu_lei="zhishu",
            zhengju_need=True,
            allow_kb=True,
            allow_web=False,
            fengxian_yinzi=0.0,
            celue_tag="kb_only",
        ),
        needs_retrieval=True,
        retrieval_strategy="auto",
        needs_pending=True,
        pending_reference="video",
        answer_mode="knowledge_grounded",
        tools_allowed=(),
    )
    main = MagicMock()
    main.pan.return_value = plan

    bundle = MagicMock()
    bundle.knowledge_block = ""
    bundle.web_block = ""
    bundle.trace = []
    bundle.pending_item = MagicMock()
    bundle.pending_item.source_type = "web_video"
    bundle.v11_pending_video_text = None
    bundle.v11_saved_to_kb = False
    bundle.v11_saved_source_id = ""
    bundle.v11_saved_title = ""
    bundle.web_judgment_reason = ""
    bundle.material_still_insufficient = True
    bundle.kb_evidence_tier = ""
    bundle.insufficiency_signal = ""
    bundle.retrieved_chunks = []
    bundle.temporary_materials = []
    bundle.bundle_id = "deadline-b1"
    bundle.material_sufficiency = "insufficient"
    bundle.execution_status = "ok"
    bundle.failures = []
    bundle.answer_limitations = []
    middle = MagicMock()

    def _slow_middle(*args: object, **kwargs: object) -> object:
        import time
        time.sleep(19.2)
        return bundle

    middle.caipan.side_effect = _slow_middle
    deps = ChatTurnDeps(
        histories={},
        session_prev_video={},
        session_pending_video={},
        lock=Lock(),
        main_agent=main,
        middle_agent=middle,
        answer_agent=MagicMock(),
        run_basic_qa=lambda *a, **k: "should not be used",
        path_fingerprint=lambda *a, **k: "fp",
        nodes_contract=lambda tr: {},
    )
    out = run_agno_chat_turn_impl("分析这个视频", session_id="deadline-video", deps=deps)
    assert "20 秒截止前返回主响应" in out["answer"]
    assert "20 秒" in out["answer"]
