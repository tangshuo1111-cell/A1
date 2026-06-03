"""Result commit runtime — unified helpers to write final task state to task store.

All async workers (video / document / web) should use these instead of calling
task_job_store directly, so that logging and future tracing hooks are centralised.
"""

from __future__ import annotations

import logging
from typing import Any

from storage import task_job_store

logger = logging.getLogger("light_maqa")


def commit_task_success(
    task_id: str,
    *,
    result_summary: dict[str, Any],
    result_pending_id: str | None = None,
) -> None:
    """Mark *task_id* as succeeded and persist *result_summary*."""
    task_job_store.mark_task_succeeded(
        task_id,
        result_summary=result_summary,
        result_pending_id=result_pending_id,
    )
    logger.info("task committed success task_id=%s", task_id)


def commit_task_failure(
    task_id: str,
    *,
    error_code: str,
    failure_reason: str,
    next_action_hint: str = "",
) -> None:
    """Mark *task_id* as failed and persist error metadata."""
    task_job_store.mark_task_failed(
        task_id,
        error_code=error_code,
        failure_reason=failure_reason,
        next_action_hint=next_action_hint,
    )
    logger.warning(
        "task committed failure task_id=%s error_code=%s", task_id, error_code
    )
