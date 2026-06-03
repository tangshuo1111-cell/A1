"""task_job_store 常量与无副作用工具（供 SQLite/PG 两实现共用）。"""

from __future__ import annotations

# 与 API / 文档统一
STATUS_PENDING = "pending"
STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_SUCCEEDED = "succeeded"
STATUS_FAILED = "failed"
STATUS_TIMEOUT = "timeout"
STATUS_CANCELLED = "cancelled"

_TERMINAL_STATUSES = frozenset(
    {STATUS_SUCCEEDED, STATUS_FAILED, STATUS_TIMEOUT, STATUS_CANCELLED}
)


def is_terminal_task_status(status: str | None) -> bool:
    return bool(status) and status in _TERMINAL_STATUSES
