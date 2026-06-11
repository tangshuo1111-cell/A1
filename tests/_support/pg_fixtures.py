"""Shared PostgreSQL fixtures: opt out of fake PG via ``@pytest.mark.pg``."""
from __future__ import annotations

import os
import socket
from urllib.parse import urlparse

import pytest

from config.settings import settings


def pg_dsn() -> str:
    return (
        os.environ.get("PYTEST_DATABASE_URL")
        or os.environ.get("DATABASE_URL")
        or ""
    ).strip()


def pg_required_marks() -> list[pytest.MarkDecorator]:
    return [
        pytest.mark.skipif(
            not pg_dsn().startswith(("postgresql://", "postgres://")),
            reason="需要 PYTEST_DATABASE_URL 或 DATABASE_URL 指向 PostgreSQL",
        ),
        pytest.mark.pg,
    ]


@pytest.fixture
def pg_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset pool to real PostgreSQL; skip when unreachable."""
    url = pg_dsn()
    monkeypatch.setattr(settings, "database_url", url)
    parsed = urlparse(url)
    if parsed.hostname:
        port = parsed.port or 5432
        try:
            with socket.create_connection((parsed.hostname, port), timeout=1.5):
                pass
        except OSError as exc:
            pytest.skip(f"PostgreSQL 端口不可达：{parsed.hostname}:{port} ({exc!s})")

    from storage import pg_pool, task_job_store
    from storage.conversation_store import reset_conversation_schema_boot_for_tests

    task_job_store.reset_task_job_store_impl_cache_for_tests()
    pg_pool.reset_pg_pool_for_tests()
    reset_conversation_schema_boot_for_tests()
    try:
        pg_pool.get_pool()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"无法连接 PostgreSQL：{exc!s}")
    yield
    pg_pool.reset_pg_pool_for_tests()
    task_job_store.reset_task_job_store_impl_cache_for_tests()
