"""main_agent：天气 / 实时网页类问句应走 external + 外链检索。"""

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


def test_guangzhou_weather_routes_external():
    d = decide(_task("帮我去天气网站查询一下广州今天的天气"))
    assert d.answer_channel == "external"
    assert d.need_external_info is True
    assert d.need_rag is False


def test_inventory_not_web():
    d = decide(_task("知识库里有什么？"))
    assert d.answer_channel == "kb"
    assert d.need_rag is True
