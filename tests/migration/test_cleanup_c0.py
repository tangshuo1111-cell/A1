"""Cleanup C0 — legacy entry import guard and audit tooling."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _run(script: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / script), *args],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_legacy_entry_guard_scripts_exist() -> None:
    assert (PROJECT_ROOT / "scripts" / "check_legacy_entry_imports.py").is_file()
    assert (PROJECT_ROOT / "scripts" / "audit_legacy_entry_symbols.py").is_file()


def test_check_legacy_entry_imports_passes() -> None:
    proc = _run("check_legacy_entry_imports.py")
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_audit_legacy_entry_symbols_passes() -> None:
    proc = _run("audit_legacy_entry_symbols.py")
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_check_readme_paths_passes() -> None:
    proc = _run("check_readme_paths.py")
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_legacy_paths_csv_lists_all_entry_modules() -> None:
    import csv

    csv_path = PROJECT_ROOT / "docs" / "current" / "migration" / "legacy_paths_status.csv"
    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    paths = {row["legacy_path"] for row in rows}
    for entry in (
        "backend/application/chat/fast_path_entry.py",
        "backend/application/chat/complex_path_entry.py",
        "backend/application/chat/async_entry.py",
    ):
        assert entry in paths
