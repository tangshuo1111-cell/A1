"""Top-level result skeleton builder."""

from __future__ import annotations

from typing import Any

from schemas import ChatTurnResult


def build_chat_turn_result(
    *,
    answer: str,
    session_id: str | None,
    request_id: str | None,
    extra: dict[str, Any],
    elapsed_ms: int,
    task_id: str | None = None,
    answer_type: str = "basic_agno",
    pipeline_ok: bool = True,
    ok: bool = True,
) -> ChatTurnResult:
    return {
        "ok": ok,
        "answer": answer,
        "session_id": session_id,
        "request_id": request_id,
        "task_id": task_id,
        "answer_type": answer_type,
        "pipeline_ok": pipeline_ok,
        "extra": extra,
        "workflow_elapsed_ms": elapsed_ms,
    }
