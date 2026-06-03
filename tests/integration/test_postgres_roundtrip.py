"""PostgreSQL 集成：任务作业 + RAG 入库/检索（需 ``DATABASE_URL`` 或 ``PYTEST_DATABASE_URL``）。"""

from __future__ import annotations

from tests._support.pg_fixtures import pg_required_marks

pytestmark = pg_required_marks()


def test_pg_task_job_roundtrip(pg_settings) -> None:  # noqa: ARG001
    from storage import task_job_store

    task_job_store.create_task("pg-int-1", task_type="t", source_type="s", user_query="hi")
    row = task_job_store.get_job("pg-int-1")
    assert row is not None
    assert row["task_type"] == "t"


def test_pg_rag_ingest_and_retrieve(pg_settings) -> None:  # noqa: ARG001
    import uuid

    from rag import ingest
    from rag.retriever import retrieve

    sid = f"int_src_{uuid.uuid4().hex[:8]}"
    n = ingest.ingest_text("alpha beta gamma uniquefixturetoken zzz", source_id=sid)
    assert n >= 1
    hits = retrieve("uniquefixturetoken", top_k=3)
    assert len(hits) >= 1
