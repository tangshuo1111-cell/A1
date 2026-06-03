"""main_agent：知识库清单类问句应走 kb+RAG。"""

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


def test_knowledge_inventory_routes_kb():
    d = decide(_task("知识库里有什么内容？"))
    assert d.answer_channel == "kb"
    assert d.need_rag is True
