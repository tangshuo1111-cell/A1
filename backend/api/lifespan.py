"""
FastAPI 生命周期：启动时校验 ``DATABASE_URL`` 并初始化 PostgreSQL 连接池，关闭时释放。

与 storage.pg_pool、config.settings 协作。不再预热 SQLite runtime。
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI


@asynccontextmanager
async def app_lifespan(_app: FastAPI) -> AsyncIterator[None]:
    from config.settings import log_runtime_bootstrap, settings
    from core.structured_logger import setup_structured_logging
    from retrieval.semantic_retriever import warmup_semantic_runtime
    from storage.pg_pool import close_pg_pool, get_pool, validate_database_url

    lvl = getattr(logging, settings.log_level, logging.INFO)
    setup_structured_logging(level=lvl)
    log_runtime_bootstrap()

    validate_database_url()
    get_pool()
    if settings.embedding_enabled:
        try:
            warmup_semantic_runtime()
        except Exception:  # noqa: BLE001
            logging.getLogger("light_maqa").warning("semantic runtime warmup failed", exc_info=True)
    yield

    close_pg_pool()
