"""Retry runtime — transient-error detection and linear back-off helpers.

Used by async workers (document / web / video) before committing a failure.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import TypeVar

R = TypeVar("R")

logger = logging.getLogger("light_maqa")

_RETRYABLE_CODES: frozenset[str] = frozenset(
    {
        "network_timeout",
        "provider_rate_limit",
        "provider_unavailable",
        "queue_full",
        "storage_temporary_error",
    }
)


def is_retryable_error(error_code: str) -> bool:
    """True when *error_code* is considered a transient failure worth retrying."""
    return error_code in _RETRYABLE_CODES


def with_linear_backoff(
    fn: Callable[[], R],
    *,
    max_attempts: int = 3,
    base_delay_sec: float = 1.0,
    task_id: str = "",
) -> R:
    """Call *fn* up to *max_attempts* times with linear back-off on failure.

    Raises RuntimeError if all attempts are exhausted.
    """
    last_exc: BaseException | None = None
    for attempt in range(max_attempts):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt < max_attempts - 1:
                delay = base_delay_sec * (attempt + 1)
                logger.warning(
                    "retry attempt=%s task_id=%s err=%s sleeping=%.1fs",
                    attempt + 1,
                    task_id,
                    exc,
                    delay,
                )
                time.sleep(delay)
    raise RuntimeError(
        f"all {max_attempts} attempts failed for task_id={task_id}"
    ) from last_exc
