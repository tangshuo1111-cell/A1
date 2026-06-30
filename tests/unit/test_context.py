import uuid
from datetime import UTC, datetime

from agents.shared.context import context_builder
from schemas import TaskInput


def test_context_empty_without_session():
    t = TaskInput(
        task_id=str(uuid.uuid4()),
        user_query="hi",
        clean_query="hi",
        has_link=False,
        link_urls=[],
        is_followup=False,
        session_id=None,
        created_at=datetime.now(UTC),
    )
    text, meta = context_builder.build_for_task(t)
    assert text == ""
    assert meta["context_hit"] is False


def test_context_meta_keys():
    t = TaskInput(
        task_id=str(uuid.uuid4()),
        user_query="hi",
        clean_query="hi",
        has_link=False,
        link_urls=[],
        is_followup=False,
        session_id="nonexistent_session_xyz",
        created_at=datetime.now(UTC),
    )
    text, meta = context_builder.build_for_task(t)
    assert "context_hit_count" in meta
    assert "context_selected_turns" in meta
    assert "context_reason" in meta


def test_context_loads_session_rows(monkeypatch):
    rows = [
        {
            "user_query": "什么是 RAG",
            "answer": "RAG 是检索增强生成，会先检索知识库再让模型回答。",
            "task_status": "success",
            "user_visible_status": "",
            "task_id": "task-001",
        },
    ]

    monkeypatch.setattr(
        "agents.shared.context.context_builder.conversation_store.load_recent_for_session",
        lambda _sid, limit=10: rows,
    )
    monkeypatch.setattr(
        "agents.shared.context.context_builder.session_memory_store.load_recent_text",
        lambda _sid: "",
    )

    t = TaskInput(
        task_id=str(uuid.uuid4()),
        user_query="继续解释 RAG",
        clean_query="继续解释 RAG",
        has_link=False,
        link_urls=[],
        is_followup=True,
        session_id="sess-abc",
        created_at=datetime.now(UTC),
    )
    text, meta = context_builder.build_for_task(t)
    assert meta["context_hit"] is True
    assert "什么是 RAG" in text
    assert "RAG 是检索增强生成" in text
    assert meta["rounds_loaded"] == 1


def test_context_store_read_failure_returns_memory_only(monkeypatch):
    monkeypatch.setattr(
        "agents.shared.context.context_builder.session_memory_store.load_recent_text",
        lambda _sid: "上一轮摘要",
    )

    def boom(*_a, **_k):
        raise RuntimeError("db unavailable")

    monkeypatch.setattr(
        "agents.shared.context.context_builder.conversation_store.load_recent_for_session",
        boom,
    )

    t = TaskInput(
        task_id=str(uuid.uuid4()),
        user_query="hi",
        clean_query="hi",
        has_link=False,
        link_urls=[],
        is_followup=False,
        session_id="sess-fail",
        created_at=datetime.now(UTC),
    )
    text, meta = context_builder.build_for_task(t)
    assert "上一轮摘要" in text
    assert meta.get("error")
    assert "读取会话失败" in meta["context_reason"]


def test_context_skips_short_failed_assistant_reply(monkeypatch):
    rows = [
        {
            "user_query": "问",
            "answer": "回答生成失败",
            "task_status": "failed",
            "user_visible_status": "",
            "task_id": "task-fail",
        },
    ]
    monkeypatch.setattr(
        "agents.shared.context.context_builder.conversation_store.load_recent_for_session",
        lambda _sid, limit=10: rows,
    )
    monkeypatch.setattr(
        "agents.shared.context.context_builder.session_memory_store.load_recent_text",
        lambda _sid: "",
    )

    t = TaskInput(
        task_id=str(uuid.uuid4()),
        user_query="继续",
        clean_query="继续",
        has_link=False,
        link_urls=[],
        is_followup=True,
        session_id="sess-skip",
        created_at=datetime.now(UTC),
    )
    text, meta = context_builder.build_for_task(t)
    assert "已省略正文" in text
    assert meta["turns_skipped"] >= 1
