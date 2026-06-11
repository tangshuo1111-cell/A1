"""Round 1 — TurnOrchestrator is the sole main-chain runtime entry."""

from __future__ import annotations

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FACADE = PROJECT_ROOT / "backend" / "application" / "chat" / "run_chat_turn.py"
ORCHESTRATOR = PROJECT_ROOT / "backend" / "application" / "chat" / "turn_orchestrator.py"
DOMAIN = PROJECT_ROOT / "backend" / "application" / "chat" / "domain"


def test_run_chat_turn_facade_is_thin() -> None:
    lines = FACADE.read_text(encoding="utf-8").splitlines()
    assert len(lines) <= 60, "run_chat_turn.py must remain a facade (Round 1)"
    text = FACADE.read_text(encoding="utf-8")
    assert "execute_turn" not in text
    assert "TurnOrchestrator" in text


def test_turn_orchestrator_has_run_entry() -> None:
    text = ORCHESTRATOR.read_text(encoding="utf-8")
    assert "class TurnOrchestrator" in text
    assert "def run(" in text
    assert "pipeline.turn_pipeline import execute_turn" in text


def test_domain_package_exports_core_models() -> None:
    expected = {
        "context.py",
        "decision.py",
        "execution_result.py",
        "runtime_state.py",
    }
    names = {p.name for p in DOMAIN.glob("*.py") if p.name != "__init__.py"}
    assert expected.issubset(names)


def test_facade_delegates_to_orchestrator() -> None:
    from application.chat.run_chat_turn import TurnOrchestrator, run_agno_chat_turn_impl
    from application.chat.turn_orchestrator import (
        TurnOrchestrator as Orch2,
        run_agno_chat_turn_impl as impl2,
    )

    assert TurnOrchestrator is Orch2
    assert run_agno_chat_turn_impl is impl2
