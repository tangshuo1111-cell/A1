"""Round 14 — stale term drift cleanup and orchestrator import hygiene."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ORCHESTRATOR = PROJECT_ROOT / "backend" / "application" / "chat" / "turn_orchestrator.py"
DEFERRED = PROJECT_ROOT / "tests" / "migration" / "deferred_cleanup_registry.json"


def _run(script: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / script), *args],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_strip_stale_terms_passes_on_scoped_paths() -> None:
    proc = _run("strip_stale_terms.py")
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_application_chat_has_no_langgraph_mentions() -> None:
    chat_root = PROJECT_ROOT / "backend" / "application" / "chat"
    for py_file in chat_root.rglob("*.py"):
        text = py_file.read_text(encoding="utf-8")
        assert "LangGraph" not in text, py_file.name
        assert "langgraph" not in text, py_file.name


def test_middle_agent_docstrings_use_current_knowledge_terms() -> None:
    runtime = (PROJECT_ROOT / "backend" / "agents" / "middle_agent" / "runtime.py").read_text(
        encoding="utf-8"
    )
    assert "agno_rag_service" not in runtime
    assert "SQLite FTS" not in runtime
    assert "retrieve_service" in runtime


def test_turn_orchestrator_no_eager_fast_path_imports() -> None:
    text = ORCHESTRATOR.read_text(encoding="utf-8")
    assert "from application.chat.fast_path_entry import" not in text
    assert "from application.chat.complex_path_entry import" not in text
    assert "from application.chat.executors.fast_executor import" not in text
    assert len(text.splitlines()) < 120
    fast_stage = PROJECT_ROOT / "backend" / "application" / "chat" / "pipeline" / "fast_stage.py"
    assert fast_stage.is_file()
    assert "AsyncExecutor.build_turn_result" in fast_stage.read_text(encoding="utf-8")


def test_deferred_registry_lists_module_size_for_r15() -> None:
    data = json.loads(DEFERRED.read_text(encoding="utf-8"))
    ids = {item["id"] for item in data["items"]}
    assert "module_size_turn_orchestrator" in ids
    assert "module_size_complex_executor" in ids
    assert "module_size_fast_executor" in ids
    for item in data["items"]:
        if item["id"].startswith("module_size_"):
            assert str(item["retire_by_round"]).startswith(("R", "post-R"))


def test_agents_md_points_to_orchestrator() -> None:
    text = (PROJECT_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "turn_orchestrator" in text
    assert "真正的编排逻辑" not in text


def test_application_readme_no_future_placeholder_ingress() -> None:
    text = (PROJECT_ROOT / "backend" / "application" / "README.md").read_text(encoding="utf-8")
    assert "未来预留" not in text
    assert "ingress/README.md" in text
