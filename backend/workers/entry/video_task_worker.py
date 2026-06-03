"""视频后台任务消费者。

职责：
- 启动本机 daemon worker 线程消费视频队列
- 将队列消息派发给统一视频后台处理服务
"""

from __future__ import annotations

import logging
import threading

from config.settings import settings
from services.capabilities.video.background_executor import process_video_background_task
from tasks.queue.video_task_queue import dequeue_video_task

logger = logging.getLogger("light_maqa")

_started_lock = threading.Lock()
_started = False


def _worker_loop(worker_index: int) -> None:
    while True:
        message = dequeue_video_task(timeout_sec=1.0)
        if message is None:
            continue
        try:
            process_video_background_task(message)
        except Exception as exc:  # noqa: BLE001
            logger.warning("video_task_worker failed idx=%s task_id=%s err=%s", worker_index, message.task_id, exc)


def ensure_video_task_workers_started() -> None:
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
                name=f"video-task-worker-{idx}",
            )
            thread.start()
        _started = True


def reset_video_task_workers_for_tests() -> None:
    global _started
    with _started_lock:
        _started = False
