"""网页 worker 池。

为网页抓取 / 动态渲染任务提供受限并发执行能力，
避免 services 层直接散落 ThreadPoolExecutor 细节。
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from typing import TypeVar

from config.settings import settings

T = TypeVar("T")
R = TypeVar("R")


def run_in_web_worker_pool(
    items: Iterable[T],
    worker_fn: Callable[[T], R],
    *,
    max_workers: int | None = None,
    thread_name_prefix: str = "web-worker",
) -> list[R]:
    """Run *worker_fn* over *items* using a bounded web worker pool."""
    item_list = list(items)
    if not item_list:
        return []
    worker_count = int(
        max_workers
        or getattr(settings, "web_parallel_workers", 2)
        or 2
    )
    worker_count = max(1, min(worker_count, len(item_list)))
    with ThreadPoolExecutor(
        max_workers=worker_count,
        thread_name_prefix=thread_name_prefix,
    ) as pool:
        return list(pool.map(worker_fn, item_list))
