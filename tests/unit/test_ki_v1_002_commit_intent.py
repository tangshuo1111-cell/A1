"""KI-V1-002 回归：is_commit_intent 收窄后，真实保存仍判 commit、分析题不再误判。"""

from __future__ import annotations

import pytest

from application.chat.approval_gate import is_commit_intent

# 真实保存命令 / 确认 → 仍应判 commit（保护原有保存意图）
COMMIT_CASES = [
    "保存",
    "请保存到知识库",
    "帮我把刚才的网页存入知识库",
    "确认保存",
    "把这个保存下来",
    "保存这个分析结果",  # 含“分析”但有祈使保存短语 → 仍 commit
    "commit",
]

# 讨论/分析“入库/保存”策略 → 不应判 commit（KI-V1-002 误拦场景）
NON_COMMIT_CASES = [
    "请综合评估『全量自动入库』与『确认后保存』两种产品策略对数据质量和复用率的影响，并给出推荐。",
    "对比自动入库和确认后保存的优缺点",
    "从冷启动、长期维护、检索质量三个维度，评估『用户确认后才保存资料』对复用率的影响",
    "自动入库和手动保存有什么区别？哪种策略更好？",
]


@pytest.mark.parametrize("msg", COMMIT_CASES)
def test_real_save_still_commit(msg: str) -> None:
    assert is_commit_intent(msg) is True


@pytest.mark.parametrize("msg", NON_COMMIT_CASES)
def test_analysis_discussion_not_commit(msg: str) -> None:
    assert is_commit_intent(msg) is False


def test_empty_message_not_commit() -> None:
    assert is_commit_intent("") is False
    assert is_commit_intent("   ") is False


def test_no_hint_not_commit() -> None:
    assert is_commit_intent("帮我总结这篇文章的重点") is False
