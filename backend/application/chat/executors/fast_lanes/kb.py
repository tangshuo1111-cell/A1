"""KB lane fast handler."""

from __future__ import annotations

from typing import Any

from application.chat.budget_clock import BudgetClock
from application.chat.executors.fast_lanes import kb_fast_impl


def run(
    *,
    ingress: Any,
    message: str,
    session_id: str | None,
    context_block: str | None,
    clock: BudgetClock,
    v13_text_content: str | None,
    v13_file_content: str | bytes | None,
    v13_title: str | None,
    shared_prep: Any | None,
) -> tuple[str, dict[str, Any]] | None:
    return kb_fast_impl.run_kb_fast_path(
        message=message,
        context_block=context_block,
        clock=clock,
        shared_prep=shared_prep,
        ingress=ingress,
    )
