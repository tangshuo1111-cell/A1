"""General fast path attempts — re-export surface (R22 split)."""

from application.chat.executors.fast_executor_general_attempt_canned import attempt_canned_fast
from application.chat.executors.fast_executor_general_attempt_llm import attempt_direct_llm_fast
from application.chat.executors.fast_executor_general_attempt_weather import attempt_weather_fast

__all__ = ["attempt_canned_fast", "attempt_direct_llm_fast", "attempt_weather_fast"]
