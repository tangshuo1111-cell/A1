def test_multi_source_research_task_runs_async_pipeline(monkeypatch) -> None:
    from services.execution import async_dispatcher
    from tasks.queue.async_task_queue import AsyncTaskMessage, reset_async_task_queue_for_tests

    reset_async_task_queue_for_tests()
    seen: dict[str, str] = {}

    monkeypatch.setattr(
        "services.execution.async_multi_source_pipeline.run_multi_source_research_task",
        lambda task_id, user_query, session_id: seen.update(
            {"task_id": task_id, "user_query": user_query, "session_id": session_id}
        ),
    )

    message = AsyncTaskMessage(
        task_id="task_multi_src",
        task_type="multi_source_research",
        lane="general",
        source_type="mixed",
        source_ref="请比较这两个来源的观点差异",
        session_id="sess-ms",
    )
    async_dispatcher.process_async_task(message)

    assert seen == {
        "task_id": "task_multi_src",
        "user_query": "请比较这两个来源的观点差异",
        "session_id": "sess-ms",
    }
