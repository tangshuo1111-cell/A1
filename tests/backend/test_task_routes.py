from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from api.main import app


def test_task_status_route_normalizes_store_row(monkeypatch):
    now = datetime.now(UTC)

    monkeypatch.setattr(
        "tasks.orchestration.task_query_service.task_job_store.get_job",
        lambda task_id: {
            "task_id": task_id,
            "status": "succeeded",
            "task_type": "web_search",
            "source_type": "web",
            "stage": "search_provider",
            "progress": 1.0,
            "session_id": "sess-1",
            "request_id": "req-1",
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "started_at": now.isoformat(),
            "finished_at": now.isoformat(),
            "duration_ms": 321.0,
            "error_code": "",
            "failure_reason": "",
            "next_action_hint": "",
            "result_pending_id": "pending-1",
            "result_source_id": "",
            "result_summary": {"status": "partial"},
        },
    )

    with TestClient(app) as client:
        r = client.get("/tasks/task-1")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["task_id"] == "task-1"
    assert body["status"] == "partial"
    assert body["raw_status"] == "succeeded"
    assert body["result_ready"] is True
    assert body["result_pending_id"] == "pending-1"


def test_task_result_route_returns_turn_answer(monkeypatch):
    now = datetime.now(UTC).isoformat()

    monkeypatch.setattr(
        "tasks.orchestration.task_query_service.task_job_store.get_job",
        lambda task_id: {
            "task_id": task_id,
            "status": "succeeded",
            "task_type": "video_asr",
            "source_type": "web_video",
            "stage": "succeeded",
            "progress": 1.0,
            "session_id": "sess-2",
            "request_id": "req-2",
            "created_at": now,
            "updated_at": now,
            "started_at": now,
            "finished_at": now,
            "duration_ms": 888.0,
            "error_code": "",
            "failure_reason": "",
            "next_action_hint": "",
            "result_pending_id": "pending-2",
            "result_source_id": "source-2",
            "result_summary": {"status": "success", "text_source": "asr"},
        },
    )
    monkeypatch.setattr(
        "tasks.orchestration.task_query_service.conversation_store.get_turn_by_task_id",
        lambda task_id: {
            "task_id": task_id,
            "answer": "这是后台任务结果",
            "answer_type": "structured_sections",
            "task_status": "succeeded",
            "user_visible_status": "后台完成",
            "has_insufficient_info_notice": "0",
        },
    )

    with TestClient(app) as client:
        r = client.get("/tasks/task-2/result")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["status"] == "succeeded"
    assert body["ready"] is True
    assert body["result"]["answer"] == "这是后台任务结果"
    assert body["result"]["summary"]["text_source"] == "asr"


def test_task_result_route_marks_expired(monkeypatch):
    finished_at = (datetime.now(UTC) - timedelta(days=8)).isoformat()

    monkeypatch.setattr(
        "tasks.orchestration.task_query_service.task_job_store.get_job",
        lambda task_id: {
            "task_id": task_id,
            "status": "succeeded",
            "task_type": "ocr",
            "source_type": "document",
            "stage": "succeeded",
            "progress": 1.0,
            "session_id": "sess-3",
            "request_id": "req-3",
            "created_at": finished_at,
            "updated_at": finished_at,
            "started_at": finished_at,
            "finished_at": finished_at,
            "duration_ms": 1000.0,
            "error_code": "",
            "failure_reason": "",
            "next_action_hint": "",
            "result_pending_id": "",
            "result_source_id": "source-3",
            "result_summary": {"status": "success"},
        },
    )
    monkeypatch.setattr(
        "tasks.orchestration.task_query_service.conversation_store.get_turn_by_task_id",
        lambda task_id: None,
    )

    with TestClient(app) as client:
        r = client.get("/tasks/task-3/result")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "expired"
    assert body["ready"] is True
    assert body["error"]["code"] == "task_expired"
