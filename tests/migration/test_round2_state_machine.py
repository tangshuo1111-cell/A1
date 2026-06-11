"""Round 2 — state machine owns TurnDecision.mode writes."""

from __future__ import annotations

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STATE_MACHINE = PROJECT_ROOT / "backend" / "application" / "chat" / "turn_state_machine.py"
DECISION = PROJECT_ROOT / "backend" / "application" / "chat" / "domain" / "decision.py"


def test_turn_decision_mode_only_mutated_in_state_machine() -> None:
    """``replace(decision, mode=...)`` must live in turn_state_machine only."""
    offenders: list[str] = []
    chat_root = PROJECT_ROOT / "backend" / "application" / "chat"
    for py_file in chat_root.rglob("*.py"):
        if py_file == STATE_MACHINE:
            continue
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (
                isinstance(func, ast.Name)
                and func.id == "replace"
                and node.keywords
            ):
                continue
            for kw in node.keywords:
                if kw.arg == "mode":
                    rel = py_file.relative_to(PROJECT_ROOT)
                    offenders.append(f"{rel}:{node.lineno}")
    assert not offenders, "TurnDecision.mode must only change in turn_state_machine:\n" + "\n".join(
        offenders
    )


def test_state_machine_and_events_modules_exist() -> None:
    assert (PROJECT_ROOT / "backend/application/chat/turn_state_machine.py").is_file()
    assert (PROJECT_ROOT / "backend/application/chat/domain/events.py").is_file()
    assert (PROJECT_ROOT / "backend/application/chat/domain/reason_codes.py").is_file()
