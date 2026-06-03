"""覆盖 middle_agent.runtime 中 logger.warning 失败分支，防止 NameError 回归。"""

from __future__ import annotations

import logging

import pytest

from agents._runtime import AgentRunFrame
from agents.main_agent.schema import AgnoCollaborationPlan, MainXiezuoPan
from agents.middle_agent.runtime import MIDDLE_PROMPT_PACK, MiddleAgentRuntime
from application.chat.budget_clock import BudgetClock
from schemas import MainDecision


def _minimal_plan() -> AgnoCollaborationPlan:
    decision = MainDecision(task_id="governance-smoke-task")
    xp = MainXiezuoPan(
        renwu_lei="zhijie",
        zhengju_need=False,
        allow_kb=False,
        allow_web=False,
        fengxian_yinzi=0.0,
        celue_tag="test",
    )
    return AgnoCollaborationPlan(
        decision=decision,
        force_skip_evidence=True,
        web_supplement_mode="explicit_only",
        answer_composition="general",
        xiezuo_pan=xp,
        needs_retrieval=False,
        needs_pending=False,
        v13_commit_intent=False,
        # 默认 tools_allowed=() 会禁止 commit_pending；此处仅测 commit 异常分支日志。
        tools_allowed=("commit_pending",),
    )


def test_invoke_executor_commit_failure_logs_warning_not_name_error(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """commit 异常分支须调用 logger.warning，不得因未定义 logger 崩溃。"""

    def _boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("commit boom for test")

    monkeypatch.setattr(
        "services.capabilities.knowledge.pending_ingestion_service.commit_most_recent_pending",
        _boom,
    )

    caplog.set_level(logging.WARNING, logger="light_maqa")

    rt = MiddleAgentRuntime()
    frame = AgentRunFrame(
        agent_mingzi="middle_agent",
        prompt_pack=MIDDLE_PROMPT_PACK,
        inputs={
            "message": "保存到知识库",
            "plan": _minimal_plan(),
            "http_use_knowledge": False,
            "history": None,
            "session_id": "gov-test-session",
            "budget_clock": BudgetClock.start(),
        },
        frame_id="gov-frame-1",
        role_signature="gov-test",
    )

    bundle = rt.invoke_executor(frame)
    assert bundle is not None
    assert any("v13 commit failed" in rec.message for rec in caplog.records)


def test_middle_runtime_logger_is_module_logger() -> None:
    from agents.middle_agent import runtime as mod

    assert getattr(mod, "logger", None) is not None
    assert isinstance(mod.logger, logging.Logger)
    assert mod.logger.name == "light_maqa"
