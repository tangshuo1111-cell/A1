"""会话级轻量记忆：追加短摘要行（PostgreSQL 唯一后端）。"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from config.settings import settings

logger = logging.getLogger("light_maqa")


def append_line(session_id: str | None, line: str) -> None:
    if not session_id or not (line or "").strip():
        return
    ts = datetime.now(UTC).isoformat()
    try:
        from storage.pg_pool import get_pool

        pool = get_pool()
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO session_memory_lines (session_id, line, created_at)
                    VALUES (%s, %s, %s);
                    """,
                    (session_id, line.strip()[:500], ts),
                )
            conn.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning("session_memory append failed: %s", e)


def load_recent_text(session_id: str | None, max_chars: int | None = None) -> str:
    if not session_id:
        return ""
    cap = max_chars if max_chars is not None else settings.session_memory_max_chars
    lines: list[str] = []
    try:
        from storage.pg_pool import get_pool

        pool = get_pool()
        with pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                    """
                    SELECT line FROM session_memory_lines
                    WHERE session_id = %s
                    ORDER BY id DESC
                    LIMIT 30;
                """,
                (session_id,),
            )
            lines = [str(r[0]) for r in cur.fetchall() if r and r[0]]
    except Exception as e:  # noqa: BLE001
        logger.warning("session_memory load failed: %s", e)
        return ""

    lines.reverse()
    parts: list[str] = []
    total = 0
    for ln in lines:
        if total + len(ln) > cap:
            break
        parts.append(ln)
        total += len(ln) + 1
    return "\n".join(parts)
