"""会话与问答记录存储（PostgreSQL 唯一后端）。"""

from __future__ import annotations

import storage.conversation_pg as cg


def reset_conversation_schema_boot_for_tests() -> None:
    """No-op：SQLite 已删除，PG schema 由 pg_pool 管理。"""


def append_turn(**kwargs) -> None:
    return cg.append_turn(**kwargs)


def get_turn_by_task_id(task_id: str):
    return cg.get_turn_by_task_id(task_id)


def load_recent_for_session(session_id: str, limit: int = 20):
    return cg.load_recent_for_session(session_id, limit=limit)
