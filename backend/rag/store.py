"""RAG 表结构初始化（PostgreSQL 唯一后端）。

PG-only since 2026-05-09，注释中的 SQLite/FTS5 表述为历史遗留。

历史遗留接口：init_schema() 确保 PG 侧 schema 就绪。
SQLite FTS5 路径已于 PG 唯一化阶段删除。
"""

from __future__ import annotations


def init_schema() -> None:
    """确认 PG 侧 rag 表已就绪（由 pg_pool._migrate_schema 管理）。"""
    from storage.pg_pool import get_pool

    get_pool()
