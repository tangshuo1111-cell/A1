"""PostgreSQL 模式下 RuntimeDbPort（不设单一全局 sqlite connection）。"""

from __future__ import annotations

from typing import Any


class PgRuntimeStubBackend:
    def get_connection(self) -> Any:
        raise RuntimeError(
            "DATABASE_URL 为 PostgreSQL 时，不要使用 runtime SQLite 全局连接。"
            "请使用 task_job_store / conversation_store / rag 入口或 storage.pg_pool。"
        )
