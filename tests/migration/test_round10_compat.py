"""Round 10 / R19 — compat shims retired; canonical paths only."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_compat_package_stub_exists() -> None:
    assert (PROJECT_ROOT / "backend" / "compat" / "__init__.py").is_file()
    assert (PROJECT_ROOT / "backend" / "legacy" / "__init__.py").is_file()


def test_draining_shim_files_removed() -> None:
    for rel in (
        "backend/compat/decide_for_agno_chat.py",
        "backend/compat/rag_service.py",
        "backend/knowledge/rag_service.py",
    ):
        assert not (PROJECT_ROOT / rel).exists(), rel


def test_decide_for_agno_chat_moved_off_runtime() -> None:
    runtime = (PROJECT_ROOT / "backend" / "agents" / "main_agent" / "runtime.py").read_text(
        encoding="utf-8"
    )
    assert "def decide_for_agno_chat" not in runtime


def test_main_agent_rule_router_still_decides() -> None:
    from entry.task_dispatcher import dispatch_task
    from agents.main_agent.rule_router import decide

    task = dispatch_task("你好", session_id="s1")
    decision = decide(task)
    assert decision.task_id


def test_history_and_evidence_shims_removed() -> None:
    assert not (PROJECT_ROOT / "backend" / "agents" / "history_context.py").exists()
    assert not (PROJECT_ROOT / "backend" / "agents" / "evidence_normalizer.py").exists()
    assert not (PROJECT_ROOT / "backend" / "compat" / "history_context.py").exists()
    assert not (PROJECT_ROOT / "backend" / "compat" / "evidence_normalizer.py").exists()


def test_main_agent_no_longer_exports_decide_for_agno_chat() -> None:
    text = (PROJECT_ROOT / "backend" / "agents" / "main_agent" / "__init__.py").read_text(encoding="utf-8")
    assert "decide_for_agno_chat" not in text


def test_check_compat_shims_script() -> None:
    proc = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / "check_compat_shims.py")],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_compat_registry_marks_r19_shims_retired() -> None:
    text = (PROJECT_ROOT / "backend" / "compat" / "compat_shim_registry.json").read_text(encoding="utf-8")
    assert '"module": "compat.decide_for_agno_chat"' in text
    assert '"module": "compat.rag_service"' in text
    assert '"module": "knowledge.rag_service"' in text
    assert '"status": "retired"' in text
    assert '"status": "retired"' in text


def test_retrieve_service_is_canonical_rag_entry() -> None:
    from services.capabilities.knowledge import retrieve_service

    assert hasattr(retrieve_service, "retrieve_knowledge")
    assert hasattr(retrieve_service, "fetch_knowledge_chunks")
