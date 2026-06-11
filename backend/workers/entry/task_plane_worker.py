from __future__ import annotations

import logging
import threading

from config.settings import settings
from services.execution.async_dispatcher import process_async_task
from storage import task_job_store
from tasks.queue.async_task_queue import dequeue_async_task

logger = logging.getLogger("light_maqa")

_started_lock = threading.Lock()
_started = False
_stop_event = threading.Event()
_threads: list[threading.Thread] = []


def _worker_loop(worker_index: int) -> None:
    while not _stop_event.is_set():
        message = dequeue_async_task(timeout_sec=1.0)
        if message is None:
            continue
        try:
            process_async_task(message)
        except Exception as exc:  # noqa: BLE001
            logger.exception("task_plane_worker failed idx=%s task_id=%s err=%s", worker_index, message.task_id, exc)
            task_job_store.mark_task_failed(
                message.task_id,
                error_code="task_worker_unhandled_exception",
                failure_reason=f"后台 worker 未处理异常: {type(exc).__name__}",
                next_action_hint="检查后台任务日志与 provider 执行栈后重试。",
            )


def ensure_task_plane_workers_started() -> None:
    global _started
    if _started:
        return
    with _started_lock:
        if _started:
            return
        _stop_event.clear()
        workers = max(1, int(getattr(settings, "v16_video_background_workers", 2) or 2))
        for idx in range(workers):
            thread = threading.Thread(
                target=_worker_loop,
                args=(idx,),
                daemon=True,
                name=f"task-plane-worker-{idx}",
            )
            thread.start()
            _threads.append(thread)
        _started = True


def reset_task_plane_workers_for_tests() -> None:
    global _started
    with _started_lock:
        _stop_event.set()
        for thread in list(_threads):
            if thread.is_alive():
                thread.join(timeout=1.2)
        _threads.clear()
        _started = False
