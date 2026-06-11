"""task_job_store 与 runtime DB 最小读写。"""

from psycopg_pool import PoolClosed
from tests._support.pg_fixtures import pg_required_marks

from storage import task_job_store


@pg_required_marks()[0]
@pg_required_marks()[1]
def test_task_job_lifecycle(pg_settings: None) -> None:  # noqa: ARG001
    tid = "unit-job-1"
    task_job_store.save_job(
        tid,
        session_id="s",
        request_id="r",
        user_query="hello",
        status=task_job_store.STATUS_PENDING,
    )
    task_job_store.mark_running(tid)
    task_job_store.update_current_node(tid, "route")
    task_job_store.mark_succeeded(tid, {"ok": True})
    row = task_job_store.get_job(tid)
    assert row is not None
    assert row["status"] == task_job_store.STATUS_SUCCEEDED
    assert row["current_node"] == "route"


def test_task_job_store_swallows_pool_closed(monkeypatch) -> None:
    monkeypatch.setattr(task_job_store._impl, "mark_task_failed", lambda *a, **k: (_ for _ in ()).throw(PoolClosed("closed")))
    monkeypatch.setattr(task_job_store._impl, "get_job", lambda *a, **k: (_ for _ in ()).throw(PoolClosed("closed")))
    monkeypatch.setattr(task_job_store._impl, "list_recent_jobs", lambda *a, **k: (_ for _ in ()).throw(PoolClosed("closed")))

    task_job_store.mark_task_failed("task-1", error_code="x", failure_reason="y")
    assert task_job_store.get_job("task-1") is None
    assert task_job_store.list_recent_jobs() == []
