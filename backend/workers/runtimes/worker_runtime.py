"""Worker runtime primitives — base daemon loop + lifecycle helpers.

Shared by video / document / web / task-plane workers.
Subclass BaseWorkerLoop and implement _dequeue / _process,
or use start_daemon_workers for a function-based approach.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Any

logger = logging.getLogger("light_maqa")


class BaseWorkerLoop:
    """Generic single-threaded daemon worker loop.

    Subclass and implement:
      - _dequeue(timeout_sec) → message | None
      - _process(message)     → None

    Call start() to spawn the daemon thread.
    """

    worker_name: str = "base-worker"

    def __init__(self, worker_index: int) -> None:
        self._index = worker_index
        self._thread: threading.Thread | None = None

    def _dequeue(self, *, timeout_sec: float = 1.0) -> Any | None:  # pragma: no cover
        raise NotImplementedError

    def _process(self, message: Any) -> None:  # pragma: no cover
        raise NotImplementedError

    def _loop(self) -> None:
        while True:
            msg = self._dequeue(timeout_sec=1.0)
            if msg is None:
                continue
            try:
                self._process(msg)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "%s idx=%s task_id=%s err=%s",
                    self.worker_name,
                    self._index,
                    getattr(msg, "task_id", "?"),
                    exc,
                )

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._loop,
            daemon=True,
            name=f"{self.worker_name}-{self._index}",
        )
        self._thread.start()


def start_daemon_workers(
    worker_count: int,
    loop_fn: Callable[[int], None],
    *,
    name_prefix: str = "worker",
) -> None:
    """Start *worker_count* daemon threads each calling loop_fn(index)."""
    for idx in range(max(1, worker_count)):
        t = threading.Thread(
            target=loop_fn,
            args=(idx,),
            daemon=True,
            name=f"{name_prefix}-{idx}",
        )
        t.start()
