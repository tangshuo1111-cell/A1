"""Startup configuration validation — single entry for lifespan."""

from __future__ import annotations

import logging

logger = logging.getLogger("light_maqa")

# Debug / diagnostic flags that must stay off in production.
_PROD_FORBIDDEN_DEBUG_FLAGS: tuple[str, ...] = (
    "ENABLE_TURN_EXIT_GATE_SHADOW",
)


def validate_production_config() -> None:
    """Fail fast when production would run with insecure or ephemeral defaults."""
    from config.settings import settings

    if settings.app_env != "prod":
        return

    errors: list[str] = []

    if not (settings.api_bearer_token or "").strip():
        errors.append("APP_ENV=prod requires API_BEARER_TOKEN")

    if not (settings.admin_api_key or "").strip():
        errors.append("APP_ENV=prod requires ADMIN_API_KEY")

    queue_backend = (settings.v16_video_task_queue_backend or "memory").strip().lower()
    if queue_backend == "memory":
        errors.append(
            "APP_ENV=prod forbids V16_VIDEO_TASK_QUEUE_BACKEND=memory; use redis"
        )
    elif queue_backend == "redis" and not (settings.v16_video_task_queue_redis_url or "").strip():
        errors.append("APP_ENV=prod requires V16_VIDEO_TASK_QUEUE_REDIS_URL when queue backend is redis")

    if settings.fake_llm_enabled:
        errors.append("APP_ENV=prod forbids LIGHT_MAQA_FAKE_LLM=1")

    from config.feature_flags import is_enabled

    for flag in _PROD_FORBIDDEN_DEBUG_FLAGS:
        if is_enabled(flag):
            errors.append(f"APP_ENV=prod forbids debug flag {flag}=1")

    if errors:
        raise RuntimeError("; ".join(errors))


def validate_startup_config() -> None:
    """Run all startup checks before serving traffic."""
    from config.feature_flags import assert_valid_flag_combination
    from storage.validate_store_backend import validate_store_backend

    assert_valid_flag_combination()
    validate_store_backend()
    validate_production_config()
    logger.info("startup config validation passed (flags + store + prod guards)")
