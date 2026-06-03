"""Platform-level async task queue abstraction."""

from __future__ import annotations

import json
import queue
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from config.settings import settings


@dataclass(frozen=True)
class AsyncTaskMessage:
    task_id: str
    task_type: str
    lane: str
    source_type: str
    source_ref: str
    request_id: str = ""
    session_id: str = ""
    payload_version: int = 1
    retry_count: int = 0
    status: str = "pending"
    enqueued_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    metadata: dict[str, Any] = field(default_factory=dict)


class _BaseAsyncTaskQueue:
    backend_name = "base"

    def enqueue(self, message: AsyncTaskMessage) -> None:  # pragma: no cover
        raise NotImplementedError

    def dequeue(self, *, timeout_sec: float = 1.0) -> AsyncTaskMessage | None:  # pragma: no cover
        raise NotImplementedError


class _InMemoryAsyncTaskQueue(_BaseAsyncTaskQueue):
    backend_name = "memory"

    def __init__(self) -> None:
        self._queue: queue.Queue[AsyncTaskMessage] = queue.Queue()

    def enqueue(self, message: AsyncTaskMessage) -> None:
        self._queue.put(message)

    def dequeue(self, *, timeout_sec: float = 1.0) -> AsyncTaskMessage | None:
        try:
            return self._queue.get(timeout=max(0.0, float(timeout_sec)))
        except queue.Empty:
            return None


class _RedisAsyncTaskQueue(_BaseAsyncTaskQueue):
    backend_name = "redis"

    def __init__(self, redis_url: str, queue_key: str) -> None:
        try:
            import redis  # type: ignore
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError("redis dependency missing") from exc
        self._client = redis.Redis.from_url(redis_url, decode_responses=True)
        self._queue_key = queue_key

    def enqueue(self, message: AsyncTaskMessage) -> None:
        self._client.lpush(self._queue_key, json.dumps(asdict(message), ensure_ascii=False))

    def dequeue(self, *, timeout_sec: float = 1.0) -> AsyncTaskMessage | None:
        item = self._client.brpop(self._queue_key, timeout=max(1, int(timeout_sec)))
        if not item:
            return None
        _, payload = item
        data = json.loads(payload or "{}")
        return AsyncTaskMessage(
            task_id=str(data.get("task_id") or ""),
            task_type=str(data.get("task_type") or ""),
            lane=str(data.get("lane") or ""),
            source_type=str(data.get("source_type") or ""),
            source_ref=str(data.get("source_ref") or ""),
            request_id=str(data.get("request_id") or ""),
            session_id=str(data.get("session_id") or ""),
            payload_version=int(data.get("payload_version") or 1),
            retry_count=int(data.get("retry_count") or 0),
            status=str(data.get("status") or "pending"),
            enqueued_at_ms=int(data.get("enqueued_at_ms") or 0),
            metadata=dict(data.get("metadata") or {}),
        )


_queue_lock = threading.Lock()
_queue_singleton: _BaseAsyncTaskQueue | None = None


def _build_queue() -> _BaseAsyncTaskQueue:
    backend = str(getattr(settings, "v16_video_task_queue_backend", "memory") or "memory").strip().lower()
    redis_url = str(getattr(settings, "v16_video_task_queue_redis_url", "") or "").strip()
    queue_key = str(getattr(settings, "v16_video_task_queue_key", "light_maqa:async_tasks") or "light_maqa:async_tasks")
    if backend == "redis" and redis_url:
        try:
            return _RedisAsyncTaskQueue(redis_url, queue_key)
        except RuntimeError:
            pass
    return _InMemoryAsyncTaskQueue()


def get_async_task_queue() -> _BaseAsyncTaskQueue:
    global _queue_singleton
    if _queue_singleton is not None:
        return _queue_singleton
    with _queue_lock:
        if _queue_singleton is None:
            _queue_singleton = _build_queue()
    return _queue_singleton


def enqueue_async_task(message: AsyncTaskMessage) -> str:
    q = get_async_task_queue()
    q.enqueue(message)
    return q.backend_name


def dequeue_async_task(*, timeout_sec: float = 1.0) -> AsyncTaskMessage | None:
    return get_async_task_queue().dequeue(timeout_sec=timeout_sec)


def reset_async_task_queue_for_tests() -> None:
    global _queue_singleton
    with _queue_lock:
        _queue_singleton = None
