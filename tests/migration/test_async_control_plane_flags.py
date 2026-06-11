from __future__ import annotations

import pytest

from config import feature_flags
from services.execution.async_runtime import ensure_async_workers_started
from services.execution.task_plane_service import (
    AsyncControlPlaneDisabledError,
    enqueue_web_heavy_fetch_task,
)
from tasks.queue.video_task_queue import VideoTaskMessage, enqueue_video_task


def test_async_flag_on_starts_task_plane_worker(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, bool] = {}
    monkeypatch.setattr(
        "workers.entry.task_plane_worker.ensure_task_plane_workers_started",
        lambda: seen.update({"task_plane": True}),
    )
    ensure_async_workers_started()
    assert seen.get("task_plane") is True


def test_async_runtime_always_uses_unified_task_plane(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, bool] = {}
    monkeypatch.setattr(
        "workers.entry.task_plane_worker.ensure_task_plane_workers_started",
        lambda: seen.update({"task_plane": True}),
    )
    ensure_async_workers_started()
    assert seen.get("task_plane") is True


def test_web_heavy_fetch_requires_async_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_ASYNC_CONTROL_PLANE_V2", False)
    with pytest.raises(AsyncControlPlaneDisabledError):
        enqueue_web_heavy_fetch_task(url="https://example.com/heavy")


def test_video_enqueue_uses_unified_queue_with_async_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    from tasks.queue import async_task_queue as queue_mod

    monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_ASYNC_CONTROL_PLANE_V2", True)
    queue_mod.reset_async_task_queue_for_tests()
    monkeypatch.setattr(
        "services.execution.async_runtime.ensure_async_workers_started",
        lambda: None,
    )
    backend = enqueue_video_task(
        VideoTaskMessage(
            task_id="p9-video",
            source_type="web_video",
            source_ref="https://example.com/v",
            session_id="sess-p9",
        )
    )
    message = queue_mod.dequeue_async_task(timeout_sec=0.01)
    assert backend == "memory"
    assert message is not None
    assert message.task_type == "video_asr_background"
    assert message.lane == "video"


def test_task_plane_worker_reset_stops_and_allows_restart(monkeypatch: pytest.MonkeyPatch) -> None:
    from workers.entry import task_plane_worker as mod

    created: list[object] = []
    joined: list[str] = []

    class _FakeThread:
        def __init__(self, *, target, args, daemon, name):  # noqa: ANN001
            self.target = target
            self.args = args
            self.daemon = daemon
            self.name = name
            self._alive = False
            created.append(self)

        def start(self) -> None:
            self._alive = True

        def is_alive(self) -> bool:
            return self._alive

        def join(self, timeout: float | None = None) -> None:
            del timeout
            self._alive = False
            joined.append(self.name)

    monkeypatch.setattr(mod.threading, "Thread", _FakeThread)
    monkeypatch.setattr(mod.settings, "v16_video_background_workers", 2)

    mod.reset_task_plane_workers_for_tests()
    mod.ensure_task_plane_workers_started()
    assert len(created) == 2
    assert mod._stop_event.is_set() is False

    mod.reset_task_plane_workers_for_tests()
    assert joined == ["task-plane-worker-0", "task-plane-worker-1"]
    assert mod._stop_event.is_set() is True

    mod.ensure_task_plane_workers_started()
    assert len(created) == 4
    assert mod._stop_event.is_set() is False

    mod.reset_task_plane_workers_for_tests()
