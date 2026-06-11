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


def test_pg_chat_session_store_survives_store_recreation(pg_settings) -> None:  # noqa: ARG001
    from domain.session_types import PendingVideoText, PrevVideoRef
    from storage.pg_chat_session_store import PgChatSessionStore

    key = "pg-session-roundtrip"
    writer = PgChatSessionStore()
    writer.clear_all()

    history = writer.get_history(key, 20)
    history.append(("user", "hello"))
    history.append(("assistant", "world"))
    writer.set_prev_video(
        key,
        PrevVideoRef(source_id="vid-1", basename="clip.mp4", path="/tmp/clip.mp4"),
    )
    writer.set_pending_video(
        key,
        PendingVideoText(
            text="transcript",
            title="clip",
            source_url="https://example.com/video",
            source_basename="clip.mp4",
            duration_sec=12.5,
            text_source="subtitle",
            subtitle_lang="zh-CN",
            asr_provider=None,
        ),
    )
    writer.persist_session(key)

    reader = PgChatSessionStore()
    restored_history = list(reader.get_history(key, 20))
    restored_prev = reader.get_prev_video(key)
    restored_pending = reader.get_pending_video(key)

    assert restored_history == [("user", "hello"), ("assistant", "world")]
    assert restored_prev is not None
    assert restored_prev.source_id == "vid-1"
    assert restored_prev.basename == "clip.mp4"
    assert restored_pending is not None
    assert restored_pending.text == "transcript"
    assert restored_pending.source_url == "https://example.com/video"

    reader.clear_all()


def test_pg_pending_store_survives_store_recreation(pg_settings) -> None:  # noqa: ARG001
    from rag.pending_schema import PendingKnowledgeItem, SourcePayload
    from storage.pg_pending_store import PgPendingStore

    store_a = PgPendingStore()
    store_a.clear_all()
    item = PendingKnowledgeItem.create(
        session_id="pg-pending-session",
        payload=SourcePayload(
            source_type="text",
            source_id="src-1",
            title="note",
            text="persist me",
            metadata={"kind": "fixture"},
            raw_source="manual",
        ),
        parser_name="pytest",
    )
    store_a.add(item)
    assert store_a.mark_committed(
        item.pending_id,
        committed_source_id="kb:src-1",
        chunk_count=2,
    )

    store_b = PgPendingStore()
    restored = store_b.get_recent("pg-pending-session", only_committable=False)
    assert restored is not None
    assert restored.pending_id == item.pending_id
    assert restored.commit_status == "committed"
    assert restored.committed_source_id == "kb:src-1"
    assert restored.committed_chunk_count == 2

    store_b.clear_all()


def test_pg_store_factory_singletons_reload_after_reset(pg_settings, monkeypatch) -> None:  # noqa: ARG001
    from config.settings import settings
    from domain.session_types import PrevVideoRef
    from storage.store_factory import get_session_store, reset_stores_for_tests

    monkeypatch.setattr(settings, "store_backend", "pg")
    reset_stores_for_tests()

    writer = get_session_store()
    history = writer.get_history("factory-session", 10)
    history.append(("user", "factory"))
    writer.set_prev_video(
        "factory-session",
        PrevVideoRef(source_id="factory-vid", basename="a.mp4", path="/tmp/a.mp4"),
    )
    writer.persist_session("factory-session")

    reset_stores_for_tests(clear_persistent=False)
    reader = get_session_store()
    restored = list(reader.get_history("factory-session", 10))
    prev = reader.get_prev_video("factory-session")

    assert restored == [("user", "factory")]
    assert prev is not None
    assert prev.source_id == "factory-vid"

    reset_stores_for_tests()
