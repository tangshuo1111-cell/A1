"""main_agent：仅贴 knowledge_samples 路径时不应被短句规则打成 direct。"""

from __future__ import annotations

from datetime import UTC, datetime

from agents.main_agent import decide
from schemas import TaskInput


def _task(q: str) -> TaskInput:
    return TaskInput(
        task_id="t",
        user_query=q,
        clean_query=q.strip(),
        created_at=datetime.now(UTC),
    )


def test_bare_short_path_triggers_tool_not_direct():
    q = "knowledge_samples/x.md"
    assert len(q) < 24
    d = decide(_task(q))
    assert d.answer_channel == "kb"
    assert d.need_tool_local is True
    assert d.need_rag is True
