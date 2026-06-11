"""Round 0 guardrails — frozen modules, import boundaries, legacy registry."""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BASELINE = PROJECT_ROOT / "tests" / "migration" / "frozen_chat_modules_baseline.json"
LEGACY_CSV = PROJECT_ROOT / "docs" / "current" / "migration" / "legacy_paths_status.csv"
IMPORT_EXCEPTIONS = PROJECT_ROOT / "docs" / "current" / "migration" / "import_exceptions.csv"


def _run(script: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / script), *args],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_frozen_chat_modules_baseline_exists() -> None:
    assert BASELINE.is_file()
    data = json.loads(BASELINE.read_text(encoding="utf-8"))
    assert "backend/application/chat/run_chat_turn.py" in data
    assert "backend/application/chat/fast_path_entry.py" not in data


def test_check_frozen_chat_modules_passes() -> None:
    proc = _run("check_frozen_chat_modules.py")
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_check_import_boundaries_passes() -> None:
    proc = _run("check_import_boundaries.py")
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_check_forbidden_legacy_imports_passes() -> None:
    proc = _run("check_forbidden_legacy_imports.py")
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_legacy_paths_status_has_round0_columns() -> None:
    with LEGACY_CSV.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows
    required = {"class", "retire_by", "forbidden_new_import"}
    assert required.issubset(set(rows[0].keys()))
    active = [r for r in rows if r.get("status") == "active"]
    assert len(active) >= 2


def test_import_exceptions_csv_present() -> None:
    assert IMPORT_EXCEPTIONS.is_file()
    text = IMPORT_EXCEPTIONS.read_text(encoding="utf-8")
    assert "violating_module" in text
    # Round 6: material_flow no longer grandfathers rag — file may be header-only
    assert "material_flow" not in text or "grandfather" not in text
