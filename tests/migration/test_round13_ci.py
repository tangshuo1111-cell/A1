"""Round 13 — CI governance scripts and contract test wiring."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CI_YML = PROJECT_ROOT / ".github" / "workflows" / "ci.yml"
MODULE_BASELINE = PROJECT_ROOT / "tests" / "migration" / "module_size_baseline.json"


def _run(script: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / script), *args],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_module_size_baseline_exists() -> None:
    assert MODULE_BASELINE.is_file()
    data = __import__("json").loads(MODULE_BASELINE.read_text(encoding="utf-8"))
    assert "backend/application/chat/turn_orchestrator.py" in data
    assert data["backend/application/chat/run_chat_turn.py"]["lines"] <= 60


def test_check_module_size_passes() -> None:
    proc = _run("check_module_size.py")
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_check_compat_field_writes_passes() -> None:
    proc = _run("check_compat_field_writes.py")
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_check_field_owner_writes_passes() -> None:
    proc = _run("check_field_owner_writes.py")
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_check_pending_store_imports_passes() -> None:
    proc = _run("check_pending_store_imports.py")
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_check_compat_consumption_passes() -> None:
    proc = _run("check_compat_consumption.py")
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_audit_test_patch_depth_passes() -> None:
    proc = _run("audit_test_patch_depth.py")
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_ci_workflow_includes_round13_guards() -> None:
    text = CI_YML.read_text(encoding="utf-8")
    assert "check_module_size.py" in text
    assert "check_compat_field_writes.py" in text
    assert "check_field_owner_writes.py" in text
    assert "check_pending_store_imports.py" in text
    assert "check_compat_consumption.py" in text
    assert "audit_test_patch_depth.py" in text
    assert "ruff format --check" in text


def test_ci_frontend_build_step() -> None:
    text = CI_YML.read_text(encoding="utf-8")
    assert "npm run build" in text


def test_docker_compose_includes_frontend_service() -> None:
    text = (PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "frontend:" in text
    assert "3000:3000" in text
    assert "BACKEND_URL: http://api:8000" in text


def test_video_cookies_route_tests_exist() -> None:
    assert (PROJECT_ROOT / "tests" / "integration" / "test_video_cookies_routes.py").is_file()


def test_proxy_allowlist_tests_exist() -> None:
    assert (PROJECT_ROOT / "frontend" / "lib" / "proxyAllowedHeaders.test.ts").is_file()
