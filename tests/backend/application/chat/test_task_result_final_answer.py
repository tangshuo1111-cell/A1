"""S9 — /tasks/{id}/result must expose final_answer on success."""
from __future__ import annotations

from unittest.mock import patch

from tasks.orchestration import task_query_service


def test_task_result_final_answer() -> None:
    task_id = "task-s9-final"
    row = {
        "task_id": task_id,
        "status": "succeeded",
        "task_type": "video_asr_background",
        "source_type": "web_video",
        "metadata": {"payload_version": 1, "lane": "video"},
        "result_summary": {
            "status": "success",
            "final_answer": "这是视频后台任务生成的最终总结。",
            "draft": True,
            "draft_limitations": ["后台草稿"],
        },
    }
    with (
        patch.object(task_query_service.task_job_store, "get_job", return_value=row),
        patch.object(task_query_service.conversation_store, "get_turn_by_task_id", return_value=None),
    ):
        payload = task_query_service.get_task_result_payload(task_id)
    assert payload is not None
    assert payload["ready"] is True
    assert payload["result"]["answer"] == "这是视频后台任务生成的最终总结。"
    assert payload["result"]["final_answer"] == "这是视频后台任务生成的最终总结。"
    assert payload["result"]["draft"] is True
    assert payload["result"]["draft_limitations"] == ["后台草稿"]


def test_task_result_missing_final_answer_when_not_ready() -> None:
    row = {
        "task_id": "task-s9-running",
        "status": "running",
        "metadata": {},
        "result_summary": {},
    }
    with (
        patch.object(task_query_service.task_job_store, "get_job", return_value=row),
        patch.object(task_query_service.conversation_store, "get_turn_by_task_id", return_value=None),
    ):
        payload = task_query_service.get_task_result_payload("task-s9-running")
    assert payload is not None
    assert payload["ready"] is False
    assert payload["result"] is None
