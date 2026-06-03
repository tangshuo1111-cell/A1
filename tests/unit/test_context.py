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
