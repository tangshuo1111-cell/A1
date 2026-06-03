"""task_job_store 与 runtime DB 最小读写。"""


from tests._support.pg_fixtures import pg_required_marks

from storage import task_job_store

pytestmark = pg_required_marks()


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
