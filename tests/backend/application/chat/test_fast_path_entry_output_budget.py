from __future__ import annotations

import sys
from types import SimpleNamespace

from application.chat.executors.fast_lanes import fast_common


def test_structured_fast_answer_uses_larger_budget_and_structured_system_prompt() -> None:
    captured: dict[str, object] = {}

    class _FakeCompletions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="1. 要点一。\n\n2. 要点二。\n\n3. 要点三。"))]
            )

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            self.chat = SimpleNamespace(completions=_FakeCompletions())

    sys.modules["openai"] = SimpleNamespace(OpenAI=_FakeClient)
    try:
        out = fast_common.run_fast_llm_answer("请按 3-5 个要点详细总结这段内容")
    finally:
        sys.modules.pop("openai", None)

    assert out.startswith("1. 要点一。")
    assert captured["max_tokens"] == 360
    messages = captured["messages"]
    assert isinstance(messages, list)
    assert "结构化结果" in messages[0]["content"]


def test_default_fast_answer_keeps_small_budget() -> None:
    captured: dict[str, object] = {}

    class _FakeCompletions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="普通回答。"))]
            )

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            self.chat = SimpleNamespace(completions=_FakeCompletions())

    sys.modules["openai"] = SimpleNamespace(OpenAI=_FakeClient)
    try:
        out = fast_common.run_fast_llm_answer("这个功能是做什么的")
    finally:
        sys.modules.pop("openai", None)

    assert out == "普通回答。"
    assert captured["max_tokens"] == 180


def test_web_page_body_summary_uses_slightly_larger_budget() -> None:
    captured: dict[str, object] = {}

    class _FakeCompletions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="网页总结。"))]
            )

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            self.chat = SimpleNamespace(completions=_FakeCompletions())

    sys.modules["openai"] = SimpleNamespace(OpenAI=_FakeClient)
    try:
        out = fast_common.summarize_fast_material(
            lane="web",
            message="请简要概括这个网页",
            material="[网页正文] example.com\nURL: https://example.com\n正文:\n这是正文内容。" * 40,
        )
    finally:
        sys.modules.pop("openai", None)

    assert out == "网页总结。"
    assert captured["max_tokens"] == 420
    messages = captured["messages"]
    assert isinstance(messages, list)
    assert "网页摘要助手" in messages[0]["content"]


def test_web_page_default_summary_prefers_bullets_and_higher_budget() -> None:
    captured: dict[str, object] = {}

    class _FakeCompletions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="1. 要点一\n2. 要点二\n3. 要点三"))]
            )

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            self.chat = SimpleNamespace(completions=_FakeCompletions())

    sys.modules["openai"] = SimpleNamespace(OpenAI=_FakeClient)
    try:
        out = fast_common.summarize_fast_material(
            lane="web",
            message="这个网页讲了什么",
            material="[网页正文] example.com\nURL: https://example.com\n正文:\n这是正文内容。" * 40,
        )
    finally:
        sys.modules.pop("openai", None)

    assert out.startswith("1. 要点一")
    assert captured["max_tokens"] == 520
    messages = captured["messages"]
    assert isinstance(messages, list)
    assert "3-5 个要点" in messages[0]["content"]
