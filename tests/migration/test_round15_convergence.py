"""Round 15 — final structure convergence and deferred cleanup closure."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CHAT_ROOT = PROJECT_ROOT / "backend" / "application" / "chat"
DEFERRED = PROJECT_ROOT / "tests" / "migration" / "deferred_cleanup_registry.json"
README = CHAT_ROOT / "README.md"


def _run(script: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / script), *args],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_deferred_registry_only_module_size_backlog() -> None:
    data = json.loads(DEFERRED.read_text(encoding="utf-8"))
    ids = {item["id"] for item in data["items"]}
    assert ids == {
        "module_size_turn_orchestrator",
        "module_size_complex_executor",
        "module_size_fast_executor",
        "module_size_fast_executor_general_attempts",
    }


def test_governance_scope_doc_exists() -> None:
    path = PROJECT_ROOT / "docs" / "current" / "migration" / "governance_scope.md"
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "non_chat_module_size_baseline" in text
    assert "check_non_chat_module_size.py" in text


def test_chat_readme_within_target_length() -> None:
    lines = README.read_text(encoding="utf-8").splitlines()
    assert len(lines) <= 120, f"chat README has {len(lines)} lines (target <=120)"


def test_domain_module_count() -> None:
    domain = CHAT_ROOT / "domain"
    py_files = {p.name for p in domain.glob("*.py") if p.name != "__init__.py"}
    required = {
        "context.py",
        "decision.py",
        "events.py",
        "execution_result.py",
        "reason_codes.py",
        "runtime_state.py",
    }
    assert required <= py_files
    assert len(py_files) <= 6


def test_executors_layout() -> None:
    executors = CHAT_ROOT / "executors"
    for name in ("fast_executor.py", "complex_executor.py", "async_executor.py"):
        assert (executors / name).is_file()
    lane_files = [p.name for p in (executors / "fast_lanes").glob("*.py") if p.name != "__init__.py"]
    assert len(lane_files) <= 14


def test_turn_orchestrator_is_canonical_entry() -> None:
    facade = (CHAT_ROOT / "run_chat_turn.py").read_text(encoding="utf-8")
    assert "TurnOrchestrator" in facade
    assert len(facade.splitlines()) <= 60


def test_all_governance_scripts_pass() -> None:
    for script in (
        "check_frozen_chat_modules.py",
        "check_import_boundaries.py",
        "check_module_size.py",
        "check_compat_shims.py",
        "check_readme_paths.py",
        "check_history_context_imports.py",
        "check_pending_store_imports.py",
        "check_compat_consumption.py",
        "check_no_pipeline_facade.py",
        "check_fast_lane_boundaries.py",
        "audit_test_patch_depth.py",
        "audit_migration_ledgers.py",
        "check_non_chat_module_size.py",
        "check_observability_health.py",
        "report_governance_status.py",
        "strip_stale_terms.py",
    ):
        proc = _run(script)
        assert proc.returncode == 0, f"{script}: {proc.stderr or proc.stdout}"


def test_phase10_deferred_cases_pass() -> None:
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/migration/test_phase10_architecture_acceptance.py::test_p10_legacy_paths_registry_coherent",
            "tests/migration/test_phase10_architecture_acceptance.py::test_kb_query_stays_in_kb_fast_lane",
            "-q",
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout or proc.stderr
