"""公开任务查询路由：供前端轮询 pending / background task。"""

from __future__ import annotations

from fastapi import APIRouter

from api.api_errors import raise_not_found
from api.schemas_http import TaskResultResponse, TaskStatusResponse
from tasks.orchestration import task_query_service

router = APIRouter()


@router.get("/{task_id}", response_model=TaskStatusResponse)
def get_task(task_id: str) -> TaskStatusResponse:
    payload = task_query_service.get_task_status_payload(task_id)
    if payload is None:
        raise_not_found("TASK_NOT_FOUND", "任务不存在")
    return TaskStatusResponse.model_validate({"ok": True, **payload})


@router.get("/{task_id}/result", response_model=TaskResultResponse)
def get_task_result(task_id: str) -> TaskResultResponse:
    payload = task_query_service.get_task_result_payload(task_id)
    if payload is None:
        raise_not_found("TASK_NOT_FOUND", "任务不存在")
    return TaskResultResponse.model_validate({"ok": True, **payload})
