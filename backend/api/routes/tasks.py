"""公开任务查询路由：供前端轮询 pending / background task。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from tasks.orchestration import task_query_service

router = APIRouter()


@router.get("/{task_id}")
def get_task(task_id: str) -> dict:
    payload = task_query_service.get_task_status_payload(task_id)
    if payload is None:
        raise HTTPException(status_code=404, detail={"code": "TASK_NOT_FOUND", "message": "任务不存在"})
    return {"ok": True, **payload}


@router.get("/{task_id}/result")
def get_task_result(task_id: str) -> dict:
    payload = task_query_service.get_task_result_payload(task_id)
    if payload is None:
        raise HTTPException(status_code=404, detail={"code": "TASK_NOT_FOUND", "message": "任务不存在"})
    return {"ok": True, **payload}
