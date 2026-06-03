"""
进程内最近任务 trace 缓存（供管理观测 `/internal/tasks/recent` 读 extra 快照使用）。

当前现状：公开 `GET /tasks/{task_id}` 已恢复；本缓存仍仅服务于内部观测合并读。
说明：非持久化；重启丢失。后续可换 Redis/DB 而不改 API 签名。
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Any

_MAX = 200
_cache: OrderedDict[str, dict[str, Any]] = OrderedDict()


def remember_task(task_id: str, payload: dict[str, Any]) -> None:
    _cache[task_id] = payload
    _cache.move_to_end(task_id)
    while len(_cache) > _MAX:
        _cache.popitem(last=False)


def get_task(task_id: str) -> dict[str, Any] | None:
    return _cache.get(task_id)
