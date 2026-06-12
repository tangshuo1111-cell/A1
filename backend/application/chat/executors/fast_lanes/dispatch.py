"""Per-lane fast path dispatch — routes to per-lane ``*_fast_impl`` modules."""

from __future__ import annotations

from typing import Any

from application.chat.budget_clock import BudgetClock
from application.chat.executors.fast_lanes import document, general, kb, video, web


def run_lane_fast_candidate(
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
    lane = str(getattr(ingress, "lane", "") or "")
    runners = {
        "video": video.run,
        "document": document.run,
        "web": web.run,
        "kb": kb.run,
        "general": general.run,
    }
    runner = runners.get(lane)
    if runner is None:
        return None
    return runner(
        ingress=ingress,
        message=message,
        session_id=session_id,
        context_block=context_block,
        clock=clock,
        v13_text_content=v13_text_content,
        v13_file_content=v13_file_content,
        v13_title=v13_title,
        shared_prep=shared_prep,
    )
