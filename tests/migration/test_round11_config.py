"""Round 11 — centralized config bootstrap and prod fail-fast."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_validate_startup_module_exists() -> None:
    from config.validate_startup import validate_production_config, validate_startup_config

    assert callable(validate_startup_config)
    assert callable(validate_production_config)


def test_lifespan_calls_validate_startup() -> None:
    text = (PROJECT_ROOT / "backend" / "api" / "lifespan.py").read_text(encoding="utf-8")
    assert "validate_startup_config" in text
    assert "validate_store_backend" not in text


def test_llm_exec_uses_settings_not_getenv() -> None:
    text = (PROJECT_ROOT / "backend" / "agents" / "answer_agent" / "llm_exec.py").read_text(
        encoding="utf-8"
    )
    assert "os.getenv" not in text
    assert "settings.fake_llm_enabled" in text


def test_settings_exposes_fake_llm_flag() -> None:
    from config.settings import settings

    assert hasattr(settings, "fake_llm_enabled")


def test_prod_fail_fast_missing_bearer(monkeypatch: pytest.MonkeyPatch) -> None:
    from config.settings import settings
    from config.validate_startup import validate_production_config

    monkeypatch.setattr(settings, "app_env", "prod")
    monkeypatch.setattr(settings, "api_bearer_token", None)
    monkeypatch.setattr(settings, "admin_api_key", "admin-secret")
    monkeypatch.setattr(settings, "v16_video_task_queue_backend", "redis")
    monkeypatch.setattr(settings, "v16_video_task_queue_redis_url", "redis://localhost:6379/0")
    monkeypatch.setattr(settings, "fake_llm_enabled", False)

    with pytest.raises(RuntimeError, match="API_BEARER_TOKEN"):
        validate_production_config()


def test_prod_fail_fast_memory_queue(monkeypatch: pytest.MonkeyPatch) -> None:
    from config.settings import settings
    from config.validate_startup import validate_production_config

    monkeypatch.setattr(settings, "app_env", "prod")
    monkeypatch.setattr(settings, "api_bearer_token", "bearer")
    monkeypatch.setattr(settings, "admin_api_key", "admin-secret")
    monkeypatch.setattr(settings, "v16_video_task_queue_backend", "memory")
    monkeypatch.setattr(settings, "fake_llm_enabled", False)

    with pytest.raises(RuntimeError, match="V16_VIDEO_TASK_QUEUE_BACKEND=memory"):
        validate_production_config()


def test_check_direct_getenv_script() -> None:
    proc = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / "check_direct_getenv.py")],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_startup_runs_flag_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    from config.feature_flags import FEATURE_FLAGS
    from config.validate_startup import validate_startup_config

    monkeypatch.setattr(
        "config.feature_flags.assert_valid_flag_combination",
        lambda flags=None: None,
    )
    monkeypatch.setattr(
        "storage.validate_store_backend.validate_store_backend",
        lambda: None,
    )
    monkeypatch.setattr(
        "config.validate_startup.validate_production_config",
        lambda: None,
    )
    validate_startup_config()
    assert FEATURE_FLAGS
