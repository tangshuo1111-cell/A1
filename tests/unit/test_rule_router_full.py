"""第三轮：`rule_router` + V10 fallback 安全网分类用例。

覆盖清单：plain / rag / web / video(链式外链) / tool / fallback。"""
from __future__ import annotations

import sys
from datetime import UTC, datetime

from tests._support.bootstrap import find_repo_root

REPO_ROOT = find_repo_root(__file__)
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agents.main_agent.main_fallback_rules import (
    _v10_fallback_intent_from_high_confidence_rules,  # noqa: E402
)
from agents.main_agent.rule_router import decide  # noqa: E402
from schemas import TaskInput  # noqa: E402


def _task(q: str, **kwargs: object) -> TaskInput:
    return TaskInput(
        task_id="full-1",
        user_query=q,
        clean_query=q,
        created_at=datetime.now(UTC),
        **kwargs,
    )


def test_category_plain_smalltalk_direct() -> None:
    d = decide(_task("嗨"))
    assert d.answer_channel == "direct"
    assert d.need_rag is False


def test_category_rag_inventory_priority() -> None:
    d = decide(_task("知识库里列出有哪些主题的文档？", has_link=False))
    assert d.need_rag is True
    assert d.answer_channel == "kb"
    assert d.middle_collect_priority == "rag_first"


def test_category_web_realtime_external() -> None:
    d = decide(_task("帮我查一下上海的天气预报"))
    assert d.answer_channel == "external"
    assert d.need_external_info is True
    assert d.need_rag is False


def test_category_video_like_url_prefers_external() -> None:
    """外链（含视频网站 URL）先入 external；不要求先 RAG。"""
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    d = decide(
        _task(
            f"解释一下这个视频在讲什么 {url}",
            has_link=True,
            link_urls=[url],
        )
    )
    assert d.answer_channel == "external"
    assert d.need_external_info is True


def test_category_tool_read_local_priority() -> None:
    """显式本地读示例 → tool_local。"""
    d = decide(_task("读取 knowledge_samples/sample.md"))
    assert d.need_tool_local is True


def test_category_fallback_v10_kb_inventory_intent() -> None:
    intent, hit = _v10_fallback_intent_from_high_confidence_rules(
        "知识库里有哪些文档可读？",
    )
    assert intent == "zhishu_yitu"
    assert hit == "asks_kb_inventory"
