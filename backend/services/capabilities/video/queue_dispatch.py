from __future__ import annotations

from services.execution.async_runtime import ensure_async_workers_started
from tasks.queue.video_task_queue import VideoTaskMessage, enqueue_video_task

from .types import VideoBackgroundTaskPayload


def enqueue_background_task(payload: VideoBackgroundTaskPayload) -> None:
    enqueue_video_task(
        VideoTaskMessage(
            task_id=payload.task_id,
            source_type=payload.source_type,
            source_ref=payload.source_ref,
            session_id=payload.session_id,
        )
    )
    ensure_async_workers_started()


def queue_web_video_asr_task(*, task_id: str, url: str, session_id: str) -> None:
    enqueue_background_task(
        VideoBackgroundTaskPayload(
            task_id=task_id,
            source_type="web_video",
            source_ref=url,
            session_id=session_id,
        )
    )


def queue_local_video_asr_task(*, task_id: str, file_path: str, session_id: str) -> None:
    enqueue_background_task(
        VideoBackgroundTaskPayload(
            task_id=task_id,
            source_type="local_video",
            source_ref=file_path,
            session_id=session_id,
        )
    )
