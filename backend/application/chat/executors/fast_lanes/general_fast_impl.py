"""General lane fast path thin coordinator."""

from __future__ import annotations

from typing import Any

from application.chat.executors.fast_lanes import fast_llm


def run_general_fast_path(
    *,
    message: str,
    context_block: str | None,
) -> tuple[str, dict[str, Any]]:
    answer_text = fast_llm.run_fast_llm_answer(message, context_block=context_block)
    return answer_text, {
        "fast_path": "general_fast",
        "lane": "general",
        "mode": "fast",
        "capabilities_called": ["capability.general.direct_answer"],
        "fast_exit_reason": "general_direct_answer",
    }
