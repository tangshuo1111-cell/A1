"""Fast executor profile — lane dispatch only."""

from __future__ import annotations

from application.chat.executors.fast_executor_delivery import (
    finalize_fast_path_delivery as _finalize_fast_path_delivery,
)
from application.chat.executors.fast_executor_general import (
    maybe_return_general_fast as _maybe_return_general_fast,
)
from application.chat.executors.fast_executor_lane import (
    maybe_return_lane_fast as _maybe_return_lane_fast,
)
from application.chat.executors.fast_executor_result import (
    maybe_return_fast_result as _maybe_return_fast_result,
)

finalize_fast_path_delivery = _finalize_fast_path_delivery
maybe_return_general_fast = _maybe_return_general_fast
maybe_return_lane_fast = _maybe_return_lane_fast
maybe_return_fast_result = _maybe_return_fast_result


class FastExecutor:
    """Fast profile — does not decide complex/async; only executes fast lanes."""

    maybe_return_general_fast = staticmethod(_maybe_return_general_fast)
    maybe_return_lane_fast = staticmethod(_maybe_return_lane_fast)
    maybe_return_fast_result = staticmethod(_maybe_return_fast_result)
