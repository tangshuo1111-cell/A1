"""Round 3 — executor split and import isolation."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_executor_modules_exist() -> None:
    base = PROJECT_ROOT / "backend" / "application" / "chat" / "executors"
    for name in ("fast_executor.py", "complex_executor.py", "async_executor.py", "types.py"):
        assert (base / name).is_file()
    for lane in ("kb.py", "web.py", "video.py", "document.py", "general.py", "dispatch.py"):
        assert (base / "fast_lanes" / lane).is_file()


def test_turn_orchestrator_imports_executors() -> None:
    orch = (PROJECT_ROOT / "backend" / "application" / "chat" / "turn_orchestrator.py").read_text(
        encoding="utf-8"
    )
    pipeline = (PROJECT_ROOT / "backend" / "application" / "chat" / "pipeline" / "turn_pipeline.py").read_text(
        encoding="utf-8"
    )
    assert "pipeline.turn_pipeline import execute_turn" in orch
    assert len(orch.splitlines()) < 120, "orchestrator should shrink after Round 3"
    for stage in ("session_stage.py", "ingress_stage.py", "fast_stage.py", "complex_stage.py"):
        assert (PROJECT_ROOT / "backend" / "application" / "chat" / "pipeline" / stage).is_file()
    assert "run_complex_stage" in pipeline
    assert "run_fast_stage" in pipeline


def test_executor_import_boundaries_pass() -> None:
    proc = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / "check_import_boundaries.py")],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_fast_executor_class_surface() -> None:
    from application.chat.executors.fast_executor import FastExecutor

    assert hasattr(FastExecutor, "maybe_return_lane_fast")
    assert hasattr(FastExecutor, "maybe_return_general_fast")
