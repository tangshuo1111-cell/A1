"""任务作业持久化（PostgreSQL 唯一后端）。"""

from __future__ import annotations

import logging
from typing import Any

from psycopg_pool import PoolClosed

import storage.task_job_store_pg_impl as _impl
from storage.task_job_constants import (  # noqa: F401 — 对外 API
    STATUS_CANCELLED,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_QUEUED,
    STATUS_RUNNING,
    STATUS_SUCCEEDED,
    STATUS_TIMEOUT,
    is_terminal_task_status,
)

logger = logging.getLogger("light_maqa")


def _call_impl(method_name: str, *args: Any, default: Any = None, **kwargs: Any) -> Any:
    method = getattr(_impl, method_name)
    try:
        return method(*args, **kwargs)
    except PoolClosed:
        logger.warning("task_job_store skipped %s because PostgreSQL pool is closed", method_name)
        return default


def reset_task_job_store_impl_cache_for_tests() -> None:
    """No-op：SQLite 双轨已删除，PG 实现直接导入。"""


def create_task(*args: Any, **kwargs: Any) -> None:
    return _call_impl("create_task", *args, **kwargs)


def update_task_async_metadata(*args: Any, **kwargs: Any) -> None:
    return _call_impl("update_task_async_metadata", *args, **kwargs)


def save_job(*args: Any, **kwargs: Any) -> None:
    return _call_impl("save_job", *args, **kwargs)


def upsert_job_started(*args: Any, **kwargs: Any) -> None:
    return _call_impl("upsert_job_started", *args, **kwargs)


def mark_running(*args: Any, **kwargs: Any) -> None:
    return _call_impl("mark_running", *args, **kwargs)


def update_current_node(*args: Any, **kwargs: Any) -> None:
    return _call_impl("update_current_node", *args, **kwargs)


def mark_succeeded(*args: Any, **kwargs: Any) -> None:
    return _call_impl("mark_succeeded", *args, **kwargs)


def mark_task_running(*args: Any, **kwargs: Any) -> None:
    return _call_impl("mark_task_running", *args, **kwargs)


def mark_task_succeeded(*args: Any, **kwargs: Any) -> None:
    return _call_impl("mark_task_succeeded", *args, **kwargs)


def mark_failed(*args: Any, **kwargs: Any) -> None:
    return _call_impl("mark_failed", *args, **kwargs)


def mark_task_failed(*args: Any, **kwargs: Any) -> None:
    return _call_impl("mark_task_failed", *args, **kwargs)


def mark_task_timeout(*args: Any, **kwargs: Any) -> None:
    return _call_impl("mark_task_timeout", *args, **kwargs)


def mark_task_cancelled(*args: Any, **kwargs: Any) -> None:
    return _call_impl("mark_task_cancelled", *args, **kwargs)


def update_task_pending_source(*args: Any, **kwargs: Any) -> None:
    return _call_impl("update_task_pending_source", *args, **kwargs)


def get_job(*args: Any, **kwargs: Any) -> Any:
    return _call_impl("get_job", *args, default=None, **kwargs)


def list_recent_jobs(*args: Any, **kwargs: Any) -> Any:
    return _call_impl("list_recent_jobs", *args, default=[], **kwargs)
