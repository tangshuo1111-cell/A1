"""文档 OCR 后台任务消费者。

职责：
- 启动专用 daemon worker 线程处理 document_ocr 任务
- 当 ENABLE_ASYNC_CONTROL_PLANE_V2=True 时，通过统一 async_dispatcher 执行
- 与 task_plane_worker 共享同一 async_task_queue，但专注于 document_ocr 类型

注意：
- document_task_worker 和 task_plane_worker 均消费 async_task_queue
- 推荐以 worker_bootstrap 统一启动，避免重复消费
"""

from __future__ import annotations

import logging
import threading

from config.settings import settings
from services.execution.async_dispatcher import process_async_task
from tasks.queue.async_task_queue import dequeue_async_task, enqueue_async_task

logger = logging.getLogger("light_maqa")

_started_lock = threading.Lock()
_started = False


def _worker_loop(worker_index: int) -> None:
    while True:
        message = dequeue_async_task(timeout_sec=1.0)
        if message is None:
            continue
        if message.task_type != "document_ocr":
            enqueue_async_task(message)
            continue
        try:
            process_async_task(message)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "document_task_worker failed idx=%s task_id=%s err=%s",
                worker_index,
                message.task_id,
                exc,
            )


def ensure_document_task_workers_started() -> None:
    global _started
    if _started:
        return
    with _started_lock:
        if _started:
            return
        workers = max(1, int(getattr(settings, "v16_video_background_workers", 2) or 2))
        for idx in range(workers):
            thread = threading.Thread(
                target=_worker_loop,
                args=(idx,),
                daemon=True,
                name=f"document-task-worker-{idx}",
            )
            thread.start()
        _started = True


def reset_document_task_workers_for_tests() -> None:
    global _started
    with _started_lock:
        _started = False
