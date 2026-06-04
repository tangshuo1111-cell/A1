"""answer_text_polish 单元测试。"""

from __future__ import annotations

import pytest

from application.chat.answer_text_polish import polish_user_answer
from config import feature_flags


@pytest.fixture(autouse=True)
def _enable_polish(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_ANSWER_TEXT_POLISH", True)


def test_polish_removes_hr_and_md_heading_keeps_emoji() -> None:
    raw = (
        "---\n"
        "### **Keyword 检索**\n"
        "- 优点：快\n\n"
        "✅ 结论：Hybrid 在模糊查询时更合适。\n"
        "⚠️ 注意：需要调参。"
    )
    out = polish_user_answer(raw)
    assert "---" not in out
    assert "###" not in out
    assert "**" not in out
    assert "✅" in out
    assert "⚠️" in out
    assert "Keyword 检索" in out


def test_polish_disabled_returns_trimmed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_ANSWER_TEXT_POLISH", False)
    raw = "  ---\n### hi  "
    assert polish_user_answer(raw) == raw.strip()
