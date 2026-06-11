"""Trace helpers for complex feedback rounds."""

from __future__ import annotations

from typing import Any

from application.chat import autonomy_loop
from application.chat.executors.complex import complex_feedback_gate as feedback_gate_mod


def trace_feedback_round(
    bundle: Any,
    *,
    plan: Any,
    round_index: int,
    trigger: str,
    requested_action: str,
    requested_by: str,
    answer_check: str,
    **kwargs: Any,
) -> Any:
    return feedback_gate_mod.append_trace(
        bundle,
        append_autonomy_trace=autonomy_loop.append_autonomy_trace,
        plan=plan,
        round_index=round_index,
        trigger=trigger,
        requested_action=requested_action,
        requested_by=requested_by,
        answer_check=answer_check,
        **kwargs,
    )
