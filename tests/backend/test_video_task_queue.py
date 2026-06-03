def test_video_task_queue_memory_backend_roundtrip(monkeypatch):
    from tasks.queue import video_task_queue as mod

    monkeypatch.setattr(mod.settings, "v16_video_task_queue_backend", "memory")
    monkeypatch.setattr(mod.settings, "v16_video_task_queue_redis_url", "")
    mod.reset_video_task_queue_for_tests()

    msg = mod.VideoTaskMessage(
        task_id="task-1",
        source_type="web_video",
        source_ref="https://example.com/v",
        session_id="sess-1",
    )
    backend = mod.enqueue_video_task(msg)
    out = mod.dequeue_video_task(timeout_sec=0.01)

    assert backend == "memory"
    assert out == msg


def test_process_video_background_task_dispatches_by_source_type(monkeypatch):
    from services.capabilities.video import background_executor as mod
    from tasks.queue.video_task_queue import VideoTaskMessage

    seen: list[tuple[str, str]] = []
    monkeypatch.setattr(
        mod,
        "run_web_video_asr_task",
        lambda task_id, url, session_id, **kwargs: seen.append(("web", url)),
    )
    monkeypatch.setattr(
        mod,
        "run_local_video_asr_task",
        lambda task_id, file_path, session_id, **kwargs: seen.append(("local", file_path)),
    )

    mod.process_video_background_task(
        VideoTaskMessage(
            task_id="task-web",
            source_type="web_video",
            source_ref="https://example.com/v",
            session_id="sess-web",
        )
    )
    mod.process_video_background_task(
        VideoTaskMessage(
            task_id="task-local",
            source_type="local_video",
            source_ref="D:/tmp/a.mp4",
            session_id="sess-local",
        )
    )

    assert ("web", "https://example.com/v") in seen
    assert ("local", "D:/tmp/a.mp4") in seen
