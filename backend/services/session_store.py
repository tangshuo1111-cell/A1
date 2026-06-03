"""会话状态存储抽象（G-024）。

当前实现为进程内 memory 版；后续可替换为 SQLite / Redis。
对外暴露 `MemorySessionStore` 实例 `default_store`，供 agno_chat_service 使用。
"""

from __future__ import annotations

import threading
from collections import deque
from typing import Protocol

from agents.history_context import PendingVideoText, PrevVideoRef


class SessionStore(Protocol):
    """会话存储协议：任何实现只需满足这几个方法即可替换。"""

    def get_history(self, key: str, max_pairs: int) -> deque[tuple[str, str]]: ...
    def get_prev_video(self, key: str) -> PrevVideoRef | None: ...
    def get_pending_video(self, key: str) -> PendingVideoText | None: ...
    def set_prev_video(self, key: str, ref: PrevVideoRef) -> None: ...
    def set_pending_video(self, key: str, pv: PendingVideoText) -> None: ...
    def pop_pending_video(self, key: str) -> None: ...
    def pop_prev_video(self, key: str) -> None: ...
    def clear_all(self) -> None: ...


class MemorySessionStore:
    """进程内 memory 实现。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._histories: dict[str, deque[tuple[str, str]]] = {}
        self._prev_video: dict[str, PrevVideoRef] = {}
        self._pending_video: dict[str, PendingVideoText] = {}

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

    def clear_all(self) -> None:
        with self._lock:
            self._histories.clear()
            self._prev_video.clear()
            self._pending_video.clear()


default_store = MemorySessionStore()
