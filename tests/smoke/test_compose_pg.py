"""
Compose / 真库冒烟（标记 ``@pytest.mark.pg``）。

- CI：已由 workflow 提供 ``DATABASE_URL`` + Postgres 服务，可直接跑。
- 本地：先 ``docker compose up -d postgres``（或与 .env 中 DATABASE_URL 一致），再：
    pytest tests/smoke/test_compose_pg.py -m pg -q
- 可选：对已启动的 API 做 HTTP 探测时设置 ``COMPOSE_SMOKE_BASE_URL=http://127.0.0.1:8000``。
"""

from __future__ import annotations

import os

import httpx
import pytest

pytestmark = pytest.mark.pg


@pytest.mark.skipif(
    not (os.environ.get("DATABASE_URL") or "").strip().startswith(
        ("postgresql://", "postgres://"),
    ),
    reason="需要 DATABASE_URL=postgresql://…（compose / CI 已注入）",
)
def test_database_url_configured() -> None:
    from config.settings import settings

    assert (settings.database_url or "").startswith(("postgresql://", "postgres://"))


@pytest.mark.skipif(
    not os.environ.get("COMPOSE_SMOKE_BASE_URL"),
    reason="可选：设 COMPOSE_SMOKE_BASE_URL 后对已启动的 api 做 /health 探测",
)
def test_compose_api_health_http() -> None:
    base = os.environ["COMPOSE_SMOKE_BASE_URL"].rstrip("/")
    with httpx.Client(timeout=10.0) as client:
        r = client.get(f"{base}/health")
    assert r.status_code == 200
    data = r.json()
    assert data.get("status") in ("ok", "degraded")
    assert "postgresql" in (data.get("checks") or {})
