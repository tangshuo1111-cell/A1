"""RAG 表结构初始化（PostgreSQL 唯一后端）。

init_schema() 确保 PG 侧 schema 就绪（实际迁移由 pg_pool._migrate_schema 管理）。
"""

from __future__ import annotations


def init_schema() -> None:
    """确认 PG 侧 rag 表已就绪（由 pg_pool._migrate_schema 管理）。"""
    from storage.pg_pool import get_pool

    get_pool()
