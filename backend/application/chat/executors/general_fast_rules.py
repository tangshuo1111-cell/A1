"""General fast lane eligibility rules."""

from __future__ import annotations

FAST_BLOCK_TOKENS = (
    "http://", "https://", "知识库", "文档", "文件", "视频", "bilibili", "youtube",
    "查网页", "搜索", "搜一下", "上网", "联网", "总结", "分析", "对比", "保存",
)


def can_use_direct_fast_path(
    message: str,
    *,
    use_knowledge: bool,
    v13_file_content: str | bytes | None,
    v13_text_content: str | None,
) -> bool:
    msg = (message or "").strip()
    if not msg or use_knowledge or v13_file_content is not None or (v13_text_content or "").strip():
        return False
    if len(msg) > 80:
        return False
    lower = msg.lower()
    return not any(token.lower() in lower for token in FAST_BLOCK_TOKENS)
