"""统一视频任务队列抽象。

第三阶段开始，长视频 / 多视频 / 超预算视频任务统一先进入这里，
再由 workers 层消费。Redis 优先；不可用时回退到进程内队列，保证开发态可直接跑通。
"""

from __future__ import annotations

from dataclasses import dataclass

from config.settings import settings  # noqa: F401 - 现有测试经本模块 settings 打桩
from tasks.queue.async_task_queue import (
    AsyncTaskMessage,
    dequeue_async_task,
    enqueue_async_task,
    reset_async_task_queue_for_tests,
)


@dataclass(frozen=True)
class VideoTaskMessage:
    task_id: str
    source_type: str
    source_ref: str
    session_id: str


def enqueue_video_task(message: VideoTaskMessage) -> str:
    return enqueue_async_task(
        AsyncTaskMessage(
            task_id=message.task_id,
            task_type="video_asr_background",
            lane="video",
            source_type=message.source_type,
            source_ref=message.source_ref,
            session_id=message.session_id,
        )
    )


def dequeue_video_task(*, timeout_sec: float = 1.0) -> VideoTaskMessage | None:
    message = dequeue_async_task(timeout_sec=timeout_sec)
    if message is None:
        return None
    if message.task_type != "video_asr_background":
        return None
    return VideoTaskMessage(
        task_id=message.task_id,
        source_type=message.source_type,
        source_ref=message.source_ref,
        session_id=message.session_id,
    )


def reset_video_task_queue_for_tests() -> None:
    reset_async_task_queue_for_tests()
