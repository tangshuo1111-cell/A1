"""
PostgreSQL 连接池与 DDL（第三轮 B-015/B-017）。

同步 psycopg + ConnectionPool；由 FastAPI lifespan 初始化/关闭。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("light_maqa")

_pool: Any = None


def pg_pool_available() -> bool:
    return _pool is not None


def _postgres_dsn_or_raise() -> str:
    """返回已 trim 的 PostgreSQL 连接串；缺失或非法则抛出明确错误。"""
    from config.settings import settings

    uri = (settings.database_url or "").strip()
    if not uri:
        raise RuntimeError(
            "DATABASE_URL 未设置。服务端仅使用 PostgreSQL，请在环境中配置 "
            "postgresql://user:password@host:5432/dbname（参见项目根 .env.example 与 docker-compose.yml）。"
        )
    if not uri.startswith(("postgresql://", "postgres://")):
        raise RuntimeError(
            "DATABASE_URL 必须为 PostgreSQL 连接串（以 postgresql:// 或 postgres:// 开头）。"
            f" 当前值无效: {uri[:64]}…"
        )
    # 缺省时缩短握手超时，避免无库时长时间挂起（可在大库 URL 中显式写 connect_timeout 覆盖）
    if "connect_timeout" not in uri and "timeout" not in uri.lower():
        sep = "&" if "?" in uri else "?"
        uri = f"{uri}{sep}connect_timeout=10"
    return uri


def validate_database_url() -> None:
    """启动契约：在创建连接池前显式校验 DSN（与 get_pool 内规则一致）。"""
    _postgres_dsn_or_raise()


def get_pool():
    """懒初始化连接池。"""
    global _pool
    if _pool is None:
        uri = _postgres_dsn_or_raise()

        try:
            from psycopg_pool import ConnectionPool
        except ImportError as e:  # pragma: no cover
            raise RuntimeError("psycopg-pool 未安装，无法使用 PostgreSQL 存储") from e

        _pool = ConnectionPool(
            conninfo=uri,
            min_size=1,
            max_size=12,
            kwargs={"autocommit": False},
            open=True,
        )
        _migrate_schema()
    return _pool


def close_pg_pool() -> None:
    global _pool
    if _pool is not None:
        try:
            _pool.close()
        except Exception:  # noqa: BLE001
            logger.exception("pg_pool close")
        _pool = None


def reset_pg_pool_for_tests() -> None:
    close_pg_pool()


def _migrate_schema() -> None:
    pool = _pool
    assert pool is not None
    stmts = [
        """
        CREATE TABLE IF NOT EXISTS app_schema_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS task_jobs (
            task_id TEXT PRIMARY KEY,
            session_id TEXT,
            request_id TEXT,
            status TEXT NOT NULL,
            current_node TEXT,
            started_at TEXT,
            finished_at TEXT,
            error_summary TEXT,
            result_summary TEXT,
            user_query_preview TEXT,
            metadata TEXT,
            task_type TEXT,
            source_type TEXT,
            stage TEXT,
            progress DOUBLE PRECISION NOT NULL DEFAULT 0,
            error_code TEXT,
            failure_reason TEXT,
            result_pending_id TEXT,
            result_source_id TEXT,
            duration_ms DOUBLE PRECISION NOT NULL DEFAULT 0,
            created_at TEXT,
            updated_at TEXT,
            next_action_hint TEXT
        );
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_task_jobs_status
        ON task_jobs (status);
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_task_jobs_started
        ON task_jobs (started_at);
        """,
        """
        CREATE TABLE IF NOT EXISTS turns (
            id BIGSERIAL PRIMARY KEY,
            task_id TEXT NOT NULL,
            session_id TEXT,
            user_query TEXT NOT NULL,
            answer TEXT NOT NULL,
            created_at TEXT NOT NULL,
            task_status TEXT DEFAULT 'done',
            answer_type TEXT DEFAULT '',
            has_insufficient_info_notice INTEGER DEFAULT 0,
            channels_used TEXT DEFAULT '[]',
            router_source TEXT DEFAULT '',
            user_visible_status TEXT DEFAULT ''
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS session_memory_lines (
            id BIGSERIAL PRIMARY KEY,
            session_id TEXT NOT NULL,
            line TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS rag_chunks (
            id BIGSERIAL PRIMARY KEY,
            source_id TEXT NOT NULL,
            content TEXT NOT NULL
        );
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_rag_chunks_source_id ON rag_chunks (source_id);
        """,
        """
        CREATE INDEX IF NOT EXISTS rag_chunks_content_tsv
        ON rag_chunks USING GIN (to_tsvector('simple', COALESCE(content, '')));
        """,
        """
        CREATE TABLE IF NOT EXISTS rag_chunk_meta (
            id BIGSERIAL PRIMARY KEY,
            chunk_id TEXT NOT NULL,
            source_id TEXT NOT NULL,
            chunk_index INTEGER NOT NULL DEFAULT 0,
            source_type TEXT NOT NULL DEFAULT 'text',
            title TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT '',
            metadata_json TEXT NOT NULL DEFAULT '{}'
        );
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_chunk_meta_source_id
        ON rag_chunk_meta (source_id);
        """,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_chunk_meta_chunk_id
        ON rag_chunk_meta (chunk_id);
        """,
        """
        CREATE TABLE IF NOT EXISTS rag_embeddings (
            rowid BIGINT PRIMARY KEY,
            dim INTEGER NOT NULL,
            vec BYTEA NOT NULL
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS turn_product_metrics (
            id BIGSERIAL PRIMARY KEY,
            task_id TEXT NOT NULL,
            session_id TEXT,
            request_id TEXT,
            created_at TEXT NOT NULL,
            task_status TEXT NOT NULL,
            mode TEXT,
            executor_profile TEXT,
            is_complex_task BOOLEAN NOT NULL DEFAULT FALSE,
            quality_gate_passed BOOLEAN,
            insufficient_evidence BOOLEAN NOT NULL DEFAULT FALSE,
            timing_total_ms INTEGER,
            answer_char_count INTEGER,
            retrieved_chunks_count INTEGER NOT NULL DEFAULT 0,
            temporary_materials_count INTEGER NOT NULL DEFAULT 0,
            failure_reason_code TEXT,
            sample_label TEXT,
            message_text TEXT,
            answer_summary TEXT
        );
        """,
        """
        ALTER TABLE turn_product_metrics ADD COLUMN IF NOT EXISTS sample_label TEXT;
        """,
        """
        ALTER TABLE turn_product_metrics ADD COLUMN IF NOT EXISTS message_text TEXT;
        """,
        """
        ALTER TABLE turn_product_metrics ADD COLUMN IF NOT EXISTS answer_summary TEXT;
        """,
        """
        ALTER TABLE turn_product_metrics ADD COLUMN IF NOT EXISTS async_final_answer TEXT;
        """,
        """
        ALTER TABLE turn_product_metrics ADD COLUMN IF NOT EXISTS async_poll_status TEXT;
        """,
        """
        ALTER TABLE turn_product_metrics ADD COLUMN IF NOT EXISTS async_background_ms INTEGER;
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_turn_product_metrics_created
        ON turn_product_metrics (created_at);
        """,
    ]
    with pool.connection() as conn:
        with conn.cursor() as cur:
            for sql in stmts:
                cur.execute(sql)
            cur.execute(
                """
                INSERT INTO app_schema_meta(key, value)
                VALUES ('runtime_schema_version', '1')
                ON CONFLICT (key) DO NOTHING;
                """
            )
        conn.commit()
    logger.info("PostgreSQL schema migration applied (version=1)")


def connection_cm():
    """供 RAG/session 等非池内长期持有：with connection_cm() as conn。"""
    return get_pool().connection()
