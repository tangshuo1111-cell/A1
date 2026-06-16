from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_project_validation_summary_profile() -> None:
    repo = Path(__file__).resolve().parents[2]
    script = repo / "scripts" / "evaluation" / "run_project_validation.py"
    proc = subprocess.run(
        [sys.executable, str(script), "--profile", "summary"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "Three validation lines" in proc.stdout
    assert "42/42" in proc.stdout
    assert "7/7" in proc.stdout
    assert "project_validation_summary.md" in proc.stdout
