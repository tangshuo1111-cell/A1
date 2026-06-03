from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from api.main import app


def test_async_task_queue_accepts_video_web_and_document_ocr(monkeypatch) -> None:
    from services.execution import async_dispatcher as dispatcher
    from tasks.queue.async_task_queue import (
        AsyncTaskMessage,
        dequeue_async_task,
        enqueue_async_task,
        reset_async_task_queue_for_tests,
    )

    reset_async_task_queue_for_tests()
    seen: list[tuple[str, str]] = []

    monkeypatch.setattr(
        dispatcher,
        "process_async_task",
        lambda message: seen.append((message.task_type, message.source_ref)),
    )

    backend = enqueue_async_task(
        AsyncTaskMessage(
            task_id="task-video",
            task_type="video_asr_background",
            lane="video",
            source_type="web_video",
            source_ref="https://example.com/v",
        )
    )
    enqueue_async_task(
        AsyncTaskMessage(
            task_id="task-web",
            task_type="web_heavy_fetch",
            lane="web",
            source_type="web_url",
            source_ref="https://example.com/article",
        )
    )
    enqueue_async_task(
        AsyncTaskMessage(
            task_id="task-doc",
            task_type="document_ocr",
            lane="document",
            source_type="document",
            source_ref="/tmp/large_scan.pdf",
        )
    )

    first = dequeue_async_task(timeout_sec=0.01)
    second = dequeue_async_task(timeout_sec=0.01)
    third = dequeue_async_task(timeout_sec=0.01)
    dispatcher.process_async_task(first)
    dispatcher.process_async_task(second)
    dispatcher.process_async_task(third)

    assert backend == "memory"
    assert ("video_asr_background", "https://example.com/v") in seen
    assert ("web_heavy_fetch", "https://example.com/article") in seen
    assert ("document_ocr", "/tmp/large_scan.pdf") in seen


def test_task_routes_expose_async_contract_fields(monkeypatch) -> None:
    from tests._support.fake_pg_pool import install_fake_pg_pool

    install_fake_pg_pool(monkeypatch)
    now = datetime.now(UTC).isoformat()
    monkeypatch.setattr(
        "tasks.orchestration.task_query_service.task_job_store.get_job",
        lambda task_id: {
            "task_id": task_id,
            "status": "succeeded",
            "task_type": "web_heavy_fetch",
            "source_type": "web_url",
            "stage": "succeeded",
            "progress": 1.0,
            "session_id": "sess-async",
            "request_id": "req-async",
            "created_at": now,
            "updated_at": now,
            "started_at": now,
            "finished_at": now,
            "duration_ms": 1200.0,
            "error_code": "",
            "failure_reason": "",
            "next_action_hint": "",
            "result_pending_id": "pending-async",
            "result_source_id": "",
            "result_summary": {"status": "success"},
            "metadata": {
                "payload_version": 1,
                "queue_backend": "memory",
                "retry_count": 0,
                "enqueued_at_ms": int(datetime.now(UTC).timestamp() * 1000) - 1200,
            },
        },
    )
    monkeypatch.setattr(
        "tasks.orchestration.task_query_service.conversation_store.get_turn_by_task_id",
        lambda task_id: {
            "task_id": task_id,
            "answer": "后台网页抓取完成",
            "answer_type": "structured_sections",
            "task_status": "succeeded",
            "user_visible_status": "后台完成",
            "has_insufficient_info_notice": "0",
        },
    )
    with TestClient(app) as client:
        r1 = client.get("/tasks/task-async")
        r2 = client.get("/tasks/task-async/result")
    assert r1.status_code == 200
    assert r2.status_code == 200
    body1 = r1.json()
    body2 = r2.json()
    assert body1["queue_backend"] == "memory"
    assert body1["payload_version"] == 1
    assert body1["retry_count"] == 0
    assert body1["task_enqueue_to_finish_ms"] >= 0
    assert body2["result"]["summary"]["status"] == "success"


def test_web_heavy_fetch_task_enters_shared_task_plane(monkeypatch) -> None:
    from services.execution import task_plane_service

    seen: dict[str, object] = {}

    monkeypatch.setattr(
        task_plane_service.task_job_store,
        "create_task",
        lambda task_id, **kw: seen.update({"task_id": task_id, "created": kw}),
    )
    monkeypatch.setattr(
        task_plane_service.task_job_store,
        "update_task_async_metadata",
        lambda task_id, metadata: seen.update({"meta_task_id": task_id, "metadata": metadata}),
    )
    monkeypatch.setattr(
        task_plane_service,
        "enqueue_async_task",
        lambda message: seen.update({"message": message}) or "memory",
    )
    monkeypatch.setattr(
        "workers.entry.task_plane_worker.ensure_task_plane_workers_started",
        lambda: seen.update({"worker_started": True}),
    )

    task_id, backend = task_plane_service.enqueue_web_heavy_fetch_task(
        url="https://example.com/heavy",
        session_id="sess-web-heavy",
        request_id="req-web-heavy",
    )

    message = seen["message"]
    assert backend == "memory"
    assert task_id == seen["task_id"]
    assert message.task_type == "web_heavy_fetch"
    assert message.lane == "web"
    assert message.source_ref == "https://example.com/heavy"
    assert seen["metadata"]["queue_backend"] == "memory"
    assert seen["worker_started"] is True
