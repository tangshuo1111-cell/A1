"""In-process session store — default for dev/tests."""

from __future__ import annotations

import threading
from collections import deque

from domain.session_types import PendingVideoText, PrevVideoRef, SessionApprovalHold


class MemoryChatSessionStore:
    """Process-local session state; same surface as legacy MemorySessionStore."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._histories: dict[str, deque[tuple[str, str]]] = {}
        self._prev_video: dict[str, PrevVideoRef] = {}
        self._pending_video: dict[str, PendingVideoText] = {}
        self._approval_hold: dict[str, SessionApprovalHold] = {}

    @property
    def lock(self) -> threading.Lock:
        return self._lock

    @property
    def histories(self) -> dict[str, deque[tuple[str, str]]]:
        return self._histories

    @property
    def session_prev_video(self) -> dict[str, PrevVideoRef]:
        return self._prev_video

    @property
    def session_pending_video(self) -> dict[str, PendingVideoText]:
        return self._pending_video

    @property
    def session_approval_hold(self) -> dict[str, SessionApprovalHold]:
        return self._approval_hold

    def ensure_session(self, key: str) -> None:
        del key

    def persist_session(self, key: str) -> None:
        del key

    def get_history(self, key: str, max_pairs: int) -> deque[tuple[str, str]]:
        with self._lock:
            return self._histories.setdefault(key, deque(maxlen=max_pairs))

    def get_prev_video(self, key: str) -> PrevVideoRef | None:
        return self._prev_video.get(key)

    def get_pending_video(self, key: str) -> PendingVideoText | None:
        return self._pending_video.get(key)

    def set_prev_video(self, key: str, ref: PrevVideoRef) -> None:
        self._prev_video[key] = ref

    def set_pending_video(self, key: str, pv: PendingVideoText) -> None:
        self._pending_video[key] = pv

    def pop_pending_video(self, key: str) -> None:
        self._pending_video.pop(key, None)

    def pop_prev_video(self, key: str) -> None:
        self._prev_video.pop(key, None)

    def get_approval_hold(self, key: str) -> SessionApprovalHold | None:
        return self._approval_hold.get(key)

    def set_approval_hold(self, key: str, hold: SessionApprovalHold) -> None:
        self._approval_hold[key] = hold

    def pop_approval_hold(self, key: str) -> None:
        self._approval_hold.pop(key, None)

    def clear_all(self) -> None:
        with self._lock:
            self._histories.clear()
            self._prev_video.clear()
            self._pending_video.clear()
            self._approval_hold.clear()
