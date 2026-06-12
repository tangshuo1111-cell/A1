"""worker 侧 task_dispatcher 入口（re-export facade）。

canonical 实现唯一落在 `entry.task_dispatcher`；本模块仅保留 worker 进程侧
`workers.entry.task_dispatcher` 这个稳定导入路径，不再复制实现，避免两份漂移。
"""

from __future__ import annotations

from entry.task_dispatcher import (  # noqa: F401 — re-export 稳定入口路径
    dispatch_task,
)

__all__ = ["dispatch_task"]
