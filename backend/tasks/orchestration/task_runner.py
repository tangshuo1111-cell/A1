"""V16 R4-E：轻量后台任务包装（守护线程），主流程可先返回 task_id。"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from typing import Any

from storage import task_job_store

logger = logging.getLogger("light_maqa")


def submit_background_task(
    task_id: str,
    worker: Callable[..., Any],
    *args: Any,
    **kwargs: Any,
) -> None:
    """在守护线程中执行 worker；异常且任务未终态时记为 failed。"""

    def _run() -> None:
        try:
            worker(*args, **kwargs)
        except Exception as e:  # noqa: BLE001
            for _ in range(10):
                try:
                    task_job_store.mark_task_failed(
                        str(task_id),
                        error_code="task_worker_exception",
                        failure_reason=f"{type(e).__name__}: {e}",
                        next_action_hint="检查任务入参或稍后重试。",
                    )
                    break
                except (OSError, RuntimeError):
                    time.sleep(0.02)
            logger.warning("v16:task_runner worker_failed task_id=%s err=%s", task_id, e)

    threading.Thread(target=_run, daemon=True).start()
