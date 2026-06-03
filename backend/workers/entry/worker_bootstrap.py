"""Worker bootstrap — 统一启动所有后台 worker 的单一入口。"""

from __future__ import annotations

import logging

logger = logging.getLogger("light_maqa")


def bootstrap_all_workers() -> None:
    """Start all async background workers once at application startup."""
    _start_unified_task_plane()


def _start_unified_task_plane() -> None:
    """Start the unified task-plane worker pool."""
    from workers.entry.task_plane_worker import ensure_task_plane_workers_started

    ensure_task_plane_workers_started()
    logger.info("worker_bootstrap: unified task-plane workers started")


def reset_all_workers_for_tests() -> None:
    """Reset all worker singleton flags — call in test teardown."""
    from workers.entry.task_plane_worker import reset_task_plane_workers_for_tests

    reset_task_plane_workers_for_tests()
