"""会话存储 PostgreSQL 实现。"""

from __future__ import annotations

import json
import logging
import time
from datetime import UTC, datetime

from psycopg import errors as pg_errors
from psycopg.rows import dict_row

from debug_trace import trace
from storage.pg_pool import get_pool

logger = logging.getLogger("light_maqa")


def append_turn(
    *,
    task_id: str,
    session_id: str | None,
    user_query: str,
    answer: str,
    task_status: str = "done",
    answer_type: str = "",
    has_insufficient_info_notice: bool = False,
    channels_used: list[str] | None = None,
    router_source: str = "",
    user_visible_status: str = "",
) -> None:
    ts = datetime.now(UTC).isoformat()
    ch_json = json.dumps(channels_used or [], ensure_ascii=False)
    trace(
        f"conversation_store.append_turn(pg) task_id={task_id} session_id={session_id!r} "
        f"status={task_status} router={router_source!r} channels={ch_json}"
    )
    pool = get_pool()
    attempts = 12
    backoff_base = 0.05
    for attempt in range(attempts):
        try:
            with pool.connection() as conn:
                with conn.cursor(row_factory=dict_row) as cur:
                    cur.execute(
                        """
                        INSERT INTO turns (
                            task_id, session_id, user_query, answer, created_at,
                            task_status, answer_type, has_insufficient_info_notice, channels_used,
                            router_source, user_visible_status
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                        """,
                        (
                            task_id,
                            session_id,
                            user_query,
                            answer,
                            ts,
                            task_status,
                            answer_type,
                            1 if has_insufficient_info_notice else 0,
                            ch_json,
                            router_source or "",
                            user_visible_status or "",
                        ),
                    )
                conn.commit()
            return
        except pg_errors.OperationalError as e:
            if "deadlock" not in str(e).lower() and "could not serialize" not in str(e).lower():
                logger.warning("conversation_store(pg) 写入失败 task_id=%s err=%s", task_id, e)
                return
            if attempt >= attempts - 1:
                logger.warning(
                    "conversation_store(pg) 写入失败（重试耗尽） task_id=%s err=%s", task_id, e
                )
                return
            time.sleep(backoff_base * (attempt + 1))
        except Exception as e:  # noqa: BLE001
            logger.warning("conversation_store(pg) 写入失败 task_id=%s err=%s", task_id, e)
            return


def get_turn_by_task_id(task_id: str) -> dict[str, str] | None:
    pool = get_pool()
    with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
                SELECT task_id, session_id, user_query, answer, created_at,
                       task_status, answer_type, has_insufficient_info_notice, channels_used,
                       router_source, user_visible_status
                FROM turns
                WHERE task_id = %s
                ORDER BY id DESC
                LIMIT 1;
                """,
            (task_id,),
        )
        row = cur.fetchone()
    if not row:
        return None
    r = dict(row)
    r["has_insufficient_info_notice"] = str(r.get("has_insufficient_info_notice", 0))
    return r


def load_recent_for_session(session_id: str, limit: int = 20) -> list[dict[str, str]]:
    pool = get_pool()
    with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
                SELECT task_id, user_query, answer, created_at, task_status, answer_type,
                       user_visible_status
                FROM turns
                WHERE session_id = %s
                ORDER BY id DESC
                LIMIT %s;
                """,
            (session_id, limit),
        )
        rows = cur.fetchall()
    out: list[dict[str, str]] = []
    for r in reversed(rows):
        d = dict(r)
        out.append(
            {
                "task_id": str(d["task_id"]),
                "user_query": str(d["user_query"]),
                "answer": str(d["answer"]),
                "created_at": str(d["created_at"]),
                "task_status": str(d.get("task_status") or ""),
                "answer_type": str(d.get("answer_type") or ""),
                "user_visible_status": str(d.get("user_visible_status") or ""),
            }
        )
    return out
