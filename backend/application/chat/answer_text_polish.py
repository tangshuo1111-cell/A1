"""用户可见回答的最后一道文本抛光（保留装饰 emoji，清理 markdown 乱格式）。"""

from __future__ import annotations

import re

from config.feature_flags import is_enabled

# 常见装饰 emoji — 明确保留
_PRESERVE_EMOJI = frozenset("✅⚠️📌🔍💡🎯📎🧠✨")

# 孤立 markdown 分隔 / 标题行
_HR_LINE = re.compile(r"^\s*-{3,}\s*$", re.MULTILINE)
_MD_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+", re.MULTILINE)
_BOLD_WRAPPER = re.compile(r"\*\*([^*\n]+)\*\*")
_EXCESS_BLANK = re.compile(r"\n{3,}")


def polish_user_answer(text: str) -> str:
    """
    清理 LLM 常见模板痕迹，保留 ✅ ⚠️ 📌 等装饰 emoji 与正文事实。

    仅在 ENABLE_ANSWER_TEXT_POLISH 开启时由 run_chat_turn 调用。
    """
    if not is_enabled("ENABLE_ANSWER_TEXT_POLISH"):
        return (text or "").strip()
    s = (text or "").strip()
    if not s:
        return s

    s = _HR_LINE.sub("", s)
    s = _MD_HEADING.sub("", s)
    s = _BOLD_WRAPPER.sub(r"\1", s)
    s = s.replace("---", " ")
    s = _EXCESS_BLANK.sub("\n\n", s)
    # 行首孤立 ### 残留
    s = re.sub(r"^\s*#{1,6}\s*", "", s, flags=re.MULTILINE)
    return s.strip()
