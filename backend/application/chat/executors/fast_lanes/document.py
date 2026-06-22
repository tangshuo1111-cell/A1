"""Document lane fast handler."""

from __future__ import annotations

from typing import Any

from application.chat.budget_clock import BudgetClock
from application.chat.executors.fast_lanes import document_fast_impl


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
    return document_fast_impl.run_document_fast_path(
        message=message,
        context_block=context_block,
        v13_text_content=v13_text_content,
        v13_file_content=v13_file_content,
        v13_title=v13_title,
        session_id=session_id,
        clock=clock,
    )
