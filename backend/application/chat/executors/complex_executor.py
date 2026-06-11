"""Complex executor profile — Main -> Middle -> Answer (Round 2)."""

from __future__ import annotations

from application.chat.executors.complex_executor_answer_stage import (
    run_answer_stage as _run_answer_stage,
)
from application.chat.executors.complex_executor_delivery import (
    run_complex_delivery_with_gate as _run_complex_delivery_with_gate,
)
from application.chat.executors.complex_executor_exit_extra import (
    build_complex_turn_result as _build_complex_turn_result,
    finalize_complex_exit_extra as _finalize_complex_exit_extra,
)
from application.chat.executors.complex_executor_main_stage import (
    run_main_stage as _run_main_stage,
)
from application.chat.executors.complex_executor_middle_stage import (
    run_middle_stage as _run_middle_stage,
)

run_complex_delivery_with_gate = _run_complex_delivery_with_gate
finalize_complex_exit_extra = _finalize_complex_exit_extra
build_complex_turn_result = _build_complex_turn_result
run_main_stage = _run_main_stage
run_middle_stage = _run_middle_stage
run_answer_stage = _run_answer_stage


class ComplexExecutor:
    """Complex profile — Main -> Middle -> Answer only."""

    run_main_stage = staticmethod(_run_main_stage)
    run_middle_stage = staticmethod(_run_middle_stage)
    run_answer_stage = staticmethod(_run_answer_stage)
    run_complex_delivery_with_gate = staticmethod(_run_complex_delivery_with_gate)
