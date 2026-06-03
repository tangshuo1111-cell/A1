"""
内部观测路由（协议层 / admin）：指标 JSON、最近任务列表。

需 ADMIN_API_KEY（若配置）；不对外公开业务细节以外的敏感数据。
与 observability.metrics、storage.task_job_store 协作。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.deps import verify_admin_optional
from observability import metrics_snapshot
from storage import task_job_store

router = APIRouter(dependencies=[Depends(verify_admin_optional)])


@router.get("/metrics")
def get_metrics() -> dict:
    return {"ok": True, **metrics_snapshot()}


@router.get("/tasks/recent")
def list_recent_tasks(limit: int = 30) -> dict:
    lim = max(1, min(limit, 200))
    items = task_job_store.list_recent_jobs(lim)
    return {"ok": True, "count": len(items), "items": items}
