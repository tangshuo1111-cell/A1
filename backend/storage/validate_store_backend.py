"""Store backend startup contract."""

from __future__ import annotations


def validate_store_backend() -> None:
    """Fail fast when production would run ephemeral chat/pending stores."""
    from config.settings import settings

    backend = (settings.store_backend or "memory").lower()
    if settings.app_env == "prod" and backend == "memory":
        raise RuntimeError(
            "APP_ENV=prod forbids STORE_BACKEND=memory; set STORE_BACKEND=pg for durable session/pending state."
        )
    if backend not in {"memory", "pg"}:
        raise RuntimeError(f"Unknown STORE_BACKEND={settings.store_backend!r}; expected memory or pg.")
