"""PostgreSQL 实现：task_job_store（同步 psycopg + 连接池）。"""

from __future__ import annotations

import contextlib
import json
from datetime import UTC, datetime
from typing import Any

from psycopg.rows import dict_row

from storage.pg_pool import get_pool
from storage.task_job_constants import (
    _TERMINAL_STATUSES,
    STATUS_CANCELLED,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_QUEUED,
    STATUS_RUNNING,
    STATUS_SUCCEEDED,
    STATUS_TIMEOUT,
)


def _cursor(conn):
    return conn.cursor(row_factory=dict_row)


def _current_status(task_id: str) -> str | None:
    row = _fetch_row(task_id)
    if not row:
        return None
    return str(row["status"] or "")


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def create_task(
    task_id: str,
    *,
    task_type: str,
    source_type: str,
    session_id: str | None = None,
    request_id: str | None = None,
    user_query: str = "",
    status: str = STATUS_QUEUED,
    stage: str = "queued",
    progress: float = 0.0,
    metadata: dict[str, Any] | None = None,
) -> None:
    now = _now_iso()
    preview = (user_query or "")[:500]
    pool = get_pool()
    with pool.connection() as conn:
        with _cursor(conn) as cur:
            cur.execute(
                """
                INSERT INTO task_jobs (
                    task_id, session_id, request_id, status, current_node,
                    started_at, finished_at, error_summary, result_summary,
                    user_query_preview, metadata, task_type, source_type, stage,
                    progress, error_code, failure_reason, result_pending_id,
                    result_source_id, duration_ms, created_at, updated_at
                )
                VALUES (
                    %s, %s, %s, %s, %s,
                    NULL, NULL, NULL, NULL,
                    %s, %s, %s, %s, %s, %s,
                    NULL, NULL, NULL, NULL, 0,
                    %s, %s
                )
                ON CONFLICT (task_id) DO UPDATE SET
                    session_id = EXCLUDED.session_id,
                    request_id = EXCLUDED.request_id,
                    status = EXCLUDED.status,
                    current_node = EXCLUDED.current_node,
                    user_query_preview = EXCLUDED.user_query_preview,
                    metadata = EXCLUDED.metadata,
                    task_type = EXCLUDED.task_type,
                    source_type = EXCLUDED.source_type,
                    stage = EXCLUDED.stage,
                    progress = EXCLUDED.progress,
                    updated_at = EXCLUDED.updated_at;
                """,
                (
                    task_id,
                    session_id,
                    request_id,
                    status,
                    stage,
                    preview,
                    json.dumps({"phase": status, **dict(metadata or {})}, ensure_ascii=False),
                    task_type,
                    source_type,
                    stage,
                    progress,
                    now,
                    now,
                ),
            )
        conn.commit()


def update_task_async_metadata(
    task_id: str,
    *,
    metadata: dict[str, Any],
) -> None:
    row = _fetch_row(task_id)
    if not row:
        return
    try:
        current = json.loads(row.get("metadata") or "{}")
    except (json.JSONDecodeError, TypeError):
        current = {}
    current.update(metadata or {})
    pool = get_pool()
    with pool.connection() as conn:
        with _cursor(conn) as cur:
            cur.execute(
                """
                UPDATE task_jobs
                SET metadata = %s, updated_at = %s
                WHERE task_id = %s;
                """,
                (json.dumps(current, ensure_ascii=False), _now_iso(), task_id),
            )
        conn.commit()


def save_job(
    task_id: str,
    *,
    session_id: str | None,
    request_id: str | None,
    user_query: str,
    status: str,
    current_node: str = "queued",
    started_at: str | None = None,
) -> None:
    create_task(
        task_id,
        task_type="legacy",
        source_type="",
        session_id=session_id,
        request_id=request_id,
        user_query=user_query,
        status=status,
        stage=current_node,
        progress=0.0 if status in (STATUS_PENDING, STATUS_QUEUED) else 0.1,
    )


def upsert_job_started(
    task_id: str,
    *,
    session_id: str | None,
    request_id: str | None,
    user_query: str,
    status: str = STATUS_RUNNING,
) -> None:
    save_job(
        task_id,
        session_id=session_id,
        request_id=request_id,
        user_query=user_query,
        status=status,
        current_node="graph",
    )


def mark_running(task_id: str) -> None:
    mark_task_running(task_id, stage="graph")


def update_current_node(task_id: str, node: str) -> None:
    pool = get_pool()
    with pool.connection() as conn:
        with _cursor(conn) as cur:
            cur.execute(
                "SELECT metadata FROM task_jobs WHERE task_id = %s;",
                (task_id,),
            )
            row = cur.fetchone()
        if not row:
            return
        try:
            m = json.loads(row["metadata"] or "{}")
        except (json.JSONDecodeError, TypeError):
            m = {}
        m["last_node"] = node
        m["last_node_at"] = _now_iso()
        with _cursor(conn) as cur:
            cur.execute(
                """
                UPDATE task_jobs
                SET current_node = %s, stage = %s, metadata = %s, updated_at = %s
                WHERE task_id = %s;
                """,
                (node, node, json.dumps(m, ensure_ascii=False), _now_iso(), task_id),
            )
        conn.commit()


def mark_succeeded(task_id: str, result_summary: dict[str, Any]) -> None:
    mark_task_succeeded(task_id, result_summary=result_summary)


def _compute_duration_ms(row: dict[str, Any] | None) -> float:
    if not row:
        return 0.0
    started = row.get("started_at")
    if not started:
        return 0.0
    try:
        dt = datetime.fromisoformat(str(started))
        return max((datetime.now(UTC) - dt).total_seconds() * 1000, 0.0)
    except ValueError:
        return 0.0


def _fetch_row(task_id: str) -> dict[str, Any] | None:
    pool = get_pool()
    with pool.connection() as conn, _cursor(conn) as cur:
        cur.execute("SELECT * FROM task_jobs WHERE task_id = %s;", (task_id,))
        return cur.fetchone()


def mark_task_running(task_id: str, *, stage: str = "running", progress: float = 0.1) -> None:
    st = _current_status(task_id)
    if st in _TERMINAL_STATUSES:
        return
    now = _now_iso()
    pool = get_pool()
    with pool.connection() as conn:
        with _cursor(conn) as cur:
            cur.execute(
                """
                UPDATE task_jobs SET
                    status = %s,
                    current_node = %s,
                    stage = %s,
                    progress = %s,
                    started_at = COALESCE(started_at, %s),
                    updated_at = %s
                WHERE task_id = %s;
                """,
                (STATUS_RUNNING, stage, stage, progress, now, now, task_id),
            )
        conn.commit()


def mark_task_succeeded(
    task_id: str,
    *,
    result_summary: dict[str, Any],
    result_pending_id: str = "",
    result_source_id: str = "",
    stage: str = "succeeded",
) -> None:
    st = _current_status(task_id)
    if st == STATUS_SUCCEEDED:
        return
    if st in (STATUS_CANCELLED, STATUS_TIMEOUT, STATUS_FAILED):
        return
    row = _fetch_row(task_id)
    current_node = str(row["current_node"] or "") if row is not None else ""
    current_node = current_node or stage
    pool = get_pool()
    with pool.connection() as conn:
        with _cursor(conn) as cur:
            cur.execute(
                """
                UPDATE task_jobs SET
                    status = %s,
                    current_node = %s,
                    stage = %s,
                    finished_at = %s,
                    result_summary = %s,
                    error_summary = NULL,
                    error_code = NULL,
                    failure_reason = NULL,
                    result_pending_id = %s,
                    result_source_id = %s,
                    progress = 1.0,
                    duration_ms = %s,
                    updated_at = %s
                WHERE task_id = %s;
                """,
                (
                    STATUS_SUCCEEDED,
                    current_node,
                    stage,
                    _now_iso(),
                    json.dumps(result_summary, ensure_ascii=False)[:12000],
                    result_pending_id,
                    result_source_id,
                    _compute_duration_ms(row),
                    _now_iso(),
                    task_id,
                ),
            )
        conn.commit()


def mark_failed(task_id: str, error_summary: str) -> None:
    mark_task_failed(task_id, error_code="task_failed", failure_reason=error_summary)


def mark_task_failed(
    task_id: str,
    *,
    error_code: str,
    failure_reason: str,
    stage: str = "failed",
    progress: float = 1.0,
    next_action_hint: str = "",
) -> None:
    st = _current_status(task_id)
    if st in _TERMINAL_STATUSES:
        return
    row = _fetch_row(task_id)
    pool = get_pool()
    with pool.connection() as conn:
        with _cursor(conn) as cur:
            cur.execute(
                """
                UPDATE task_jobs SET
                    status = %s,
                    current_node = %s,
                    stage = %s,
                    finished_at = %s,
                    error_summary = %s,
                    error_code = %s,
                    failure_reason = %s,
                    next_action_hint = %s,
                    progress = %s,
                    duration_ms = %s,
                    updated_at = %s
                WHERE task_id = %s;
                """,
                (
                    STATUS_FAILED,
                    stage,
                    stage,
                    _now_iso(),
                    failure_reason[:4000],
                    error_code[:200],
                    failure_reason[:4000],
                    (next_action_hint or "")[:4000],
                    progress,
                    _compute_duration_ms(row),
                    _now_iso(),
                    task_id,
                ),
            )
        conn.commit()


def mark_task_timeout(
    task_id: str,
    *,
    failure_reason: str = "task timeout",
    next_action_hint: str = "",
) -> None:
    st = _current_status(task_id)
    if st in _TERMINAL_STATUSES:
        return
    row = _fetch_row(task_id)
    pool = get_pool()
    with pool.connection() as conn:
        with _cursor(conn) as cur:
            cur.execute(
                """
                UPDATE task_jobs SET
                    status = %s,
                    current_node = %s,
                    stage = %s,
                    finished_at = %s,
                    error_summary = %s,
                    error_code = %s,
                    failure_reason = %s,
                    next_action_hint = %s,
                    progress = 1.0,
                    duration_ms = %s,
                    updated_at = %s
                WHERE task_id = %s;
                """,
                (
                    STATUS_TIMEOUT,
                    "timeout",
                    "timeout",
                    _now_iso(),
                    failure_reason[:4000],
                    "task_timeout",
                    failure_reason[:4000],
                    (next_action_hint or "")[:4000],
                    _compute_duration_ms(row),
                    _now_iso(),
                    task_id,
                ),
            )
        conn.commit()


def mark_task_cancelled(
    task_id: str,
    *,
    failure_reason: str = "task cancelled",
    next_action_hint: str = "",
) -> None:
    st = _current_status(task_id)
    if st in _TERMINAL_STATUSES:
        return
    row = _fetch_row(task_id)
    pool = get_pool()
    with pool.connection() as conn:
        with _cursor(conn) as cur:
            cur.execute(
                """
                UPDATE task_jobs SET
                    status = %s,
                    current_node = %s,
                    stage = %s,
                    finished_at = %s,
                    error_summary = %s,
                    error_code = %s,
                    failure_reason = %s,
                    next_action_hint = %s,
                    progress = 1.0,
                    duration_ms = %s,
                    updated_at = %s
                WHERE task_id = %s;
                """,
                (
                    STATUS_CANCELLED,
                    "cancelled",
                    "cancelled",
                    _now_iso(),
                    failure_reason[:4000],
                    "task_cancelled",
                    failure_reason[:4000],
                    (next_action_hint or "")[:4000],
                    _compute_duration_ms(row),
                    _now_iso(),
                    task_id,
                ),
            )
        conn.commit()


def update_task_pending_source(
    task_id: str,
    *,
    result_pending_id: str = "",
    result_source_id: str = "",
) -> None:
    st = _current_status(task_id)
    if st in (STATUS_FAILED, STATUS_TIMEOUT, STATUS_CANCELLED):
        return
    if result_source_id and st != STATUS_SUCCEEDED:
        return
    sets: list[str] = []
    args: list[Any] = []
    if result_pending_id:
        sets.append("result_pending_id = %s")
        args.append(result_pending_id)
    if result_source_id:
        sets.append("result_source_id = %s")
        args.append(result_source_id)
    if not sets:
        return
    args.append(_now_iso())
    args.append(task_id)
    pool = get_pool()
    with pool.connection() as conn:
        with _cursor(conn) as cur:
            cur.execute(
                f"""
                UPDATE task_jobs SET
                    {", ".join(sets)},
                    updated_at = %s
                WHERE task_id = %s;
                """,
                tuple(args),
            )
        conn.commit()


def get_job(task_id: str) -> dict[str, Any] | None:
    pool = get_pool()
    with pool.connection() as conn, _cursor(conn) as cur:
        cur.execute("SELECT * FROM task_jobs WHERE task_id = %s;", (task_id,))
        row = cur.fetchone()
    if not row:
        return None
    d = dict(row)
    for k in ("result_summary", "metadata"):
        if d.get(k) and isinstance(d[k], str):
            try:  # noqa: SIM105
                d[k] = json.loads(d[k])
            except json.JSONDecodeError:
                pass
    return d


def list_recent_jobs(limit: int = 50) -> list[dict[str, Any]]:
    pool = get_pool()
    with pool.connection() as conn, _cursor(conn) as cur:
        cur.execute(
            """
                SELECT task_id, session_id, request_id, status, current_node,
                       started_at, finished_at, user_query_preview, task_type,
                       source_type, stage, progress, error_code, result_pending_id,
                       result_source_id, created_at, updated_at, metadata, result_summary
                FROM task_jobs
                ORDER BY COALESCE(finished_at, started_at) DESC NULLS LAST
                LIMIT %s;
                """,
            (limit,),
        )
        rows = [dict(r) for r in cur.fetchall()]
        for row in rows:
            for key in ("metadata", "result_summary"):
                value = row.get(key)
                if isinstance(value, str):
                    with contextlib.suppress(json.JSONDecodeError):
                        row[key] = json.loads(value)
        return rows
