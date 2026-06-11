"""General lane fast path thin coordinator."""

from __future__ import annotations

from application.chat.executors.fast_lanes import fast_llm
from application.chat.executors.general_fast_rules import can_use_direct_fast_path
from application.chat.executors.general_fast_terms import (
    LOCAL_TERM_EXPLAINS,
    try_canned_fast_answer,
)
from application.chat.executors.general_fast_weather import (
    WEATHER_CITY_MAP,
    try_fast_weather_answer,
    weather_city_from_message,
    weather_desc,
)


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
