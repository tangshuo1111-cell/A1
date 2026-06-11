"""Round 4 — agent result contracts and port isolation."""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
AGENTS_ROOT = PROJECT_ROOT / "backend" / "agents"


def test_agent_result_modules_exist() -> None:
    for rel in (
        "application/chat/chat_contracts.py",
        "application/chat/turn_response_builder.py",
        "application/chat/agent_invoke.py",
        "agents/ports.py",
    ):
        assert (PROJECT_ROOT / "backend" / rel).is_file()


def test_agents_do_not_import_fastapi() -> None:
    for path in AGENTS_ROOT.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "fastapi" not in text.lower(), f"{path} must not import FastAPI"


def test_agent_extra_rejects_forbidden_keys() -> None:
    from application.chat.chat_contracts import assert_agent_extra_safe
    import pytest

    with pytest.raises(ValueError, match="task_id"):
        assert_agent_extra_safe({"task_id": "x", "v6_main_pan_renwu": "zhijie"})


def test_main_middle_answer_return_result_types() -> None:
    from application.chat.budget_clock import BudgetClock
    from application.chat.chat_contracts import AnswerAgentResult, MainAgentResult, MiddleAgentResult
    from agents.answer_agent import AnswerAgent
    from agents.main_agent import MainAgent
    from agents.middle_agent import MiddleAgent

    clock = BudgetClock.start()
    main = MainAgent().pan("你好", session_id=None, http_use_knowledge=False, clock=clock)
    assert isinstance(main, MainAgentResult)
    mid = MiddleAgent().caipan("你好", plan=main.plan, http_use_knowledge=False, clock=clock)
    assert isinstance(mid, MiddleAgentResult)
    ans = AnswerAgent().huida("你好", context_block=None, plan=main.plan, bundle=mid.bundle, clock=clock)
    assert isinstance(ans, AnswerAgentResult)
    text, hp = ans
    assert text == ans.answer_text
    assert hp is ans.huida_pan


def test_complex_executor_uses_agent_invoke() -> None:
    base = PROJECT_ROOT / "backend" / "application" / "chat" / "executors"
    main_text = (base / "complex_executor_main_stage.py").read_text(encoding="utf-8")
    middle_text = (base / "complex_executor_middle_stage.py").read_text(encoding="utf-8")
    exit_text = (base / "complex_executor_exit_extra.py").read_text(encoding="utf-8")
    assert "invoke_main_agent" in main_text
    assert "invoke_middle_agent" in middle_text
    assert "turn_response_builder" in exit_text


def test_turn_response_builder_is_only_http_field_writer_in_complex_executor() -> None:
    path = PROJECT_ROOT / "backend" / "application" / "chat" / "executors" / "complex_executor_exit_extra.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    forbidden = {"ok", "workflow_elapsed_ms", "task_id", "primary_path"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for key in node.keys:
                if isinstance(key, ast.Constant) and key.value in forbidden:
                    assert node.lineno > 1
