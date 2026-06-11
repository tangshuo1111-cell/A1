"""Cleanup C1–C3 — legacy entry shells and zero production imports."""

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


def test_legacy_entry_shells_removed() -> None:
    for rel in (
        "backend/application/chat/fast_path_entry.py",
        "backend/application/chat/complex_path_entry.py",
        "backend/application/chat/async_entry.py",
    ):
        assert not (PROJECT_ROOT / rel).is_file(), f"legacy shell still present: {rel}"


def test_canonical_impl_modules_exist() -> None:
    base = PROJECT_ROOT / "backend" / "application" / "chat" / "executors"
    lanes = base / "fast_lanes"
    assert not (lanes / "fast_path_impl.py").is_file()
    for name in (
        "fast_common.py",
        "kb_fast_impl.py",
        "web_fast_impl.py",
        "video_fast_impl.py",
        "document_fast_impl.py",
        "general_fast_impl.py",
    ):
        assert (lanes / name).is_file(), name
    assert (base / "fast_delivery.py").is_file()
    complex_pkg = base / "complex"
    assert (complex_pkg / "complex_path_impl.py").is_file()
    for name in (
        "complex_deadline.py",
        "complex_multisource_impl.py",
        "complex_feedback_impl.py",
        "complex_feedback_synthesize.py",
    ):
        assert (complex_pkg / name).is_file(), name
    for name in (
        "complex_executor_delivery.py",
        "complex_executor_exit_extra.py",
        "complex_executor_main_stage.py",
        "complex_executor_middle_stage.py",
        "complex_executor_answer_stage.py",
    ):
        assert (base / name).is_file(), name
    assert (base / "async_path" / "build_pending.py").is_file()
    pipeline = PROJECT_ROOT / "backend" / "application" / "chat" / "pipeline"
    for name in (
        "turn_pipeline.py",
        "session_stage.py",
        "ingress_stage.py",
        "fast_stage.py",
        "complex_stage.py",
    ):
        assert (pipeline / name).is_file(), name
    orch = (PROJECT_ROOT / "backend" / "application" / "chat" / "turn_orchestrator.py").read_text(
        encoding="utf-8"
    )
    assert "_LAZY_REEXPORTS" not in orch
    assert "def __getattr__" not in orch
    pipeline_dir = PROJECT_ROOT / "backend" / "application" / "chat" / "pipeline"
    for stage in pipeline_dir.glob("*.py"):
        text = stage.read_text(encoding="utf-8")
        assert "_ChatFacade" not in text, stage.name
        assert "facade = _ChatFacade" not in text, stage.name


def test_production_does_not_import_fast_path_impl() -> None:
    for rel in (
        "backend/application/chat/executors/fast_executor.py",
        "backend/application/chat/executors/fast_lanes/kb.py",
        "backend/application/chat/executors/fast_lanes/dispatch.py",
    ):
        text = (PROJECT_ROOT / rel).read_text(encoding="utf-8")
        assert "fast_path_impl" not in text, rel


def test_production_has_zero_legacy_entry_imports() -> None:
    proc = _run("check_legacy_entry_imports.py")
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_executors_do_not_import_legacy_entry_modules() -> None:
    for rel in (
        "backend/application/chat/executors/fast_executor.py",
        "backend/application/chat/executors/complex_executor.py",
        "backend/application/chat/executors/async_executor.py",
    ):
        text = (PROJECT_ROOT / rel).read_text(encoding="utf-8")
        assert "fast_path_entry" not in text, rel
        assert "complex_path_entry" not in text, rel
        assert "async_entry" not in text, rel
