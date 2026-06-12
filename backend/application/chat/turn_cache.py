"""Within-turn memoization — avoid duplicate KB/probe work in one chat turn (§6.5 / R6)."""
from __future__ import annotations

from collections.abc import Callable
from contextvars import ContextVar, Token
from typing import Any, TypeVar

from config.feature_flags import is_enabled

T = TypeVar("T")

_turn_cache_ctx: ContextVar[TurnCache | None] = ContextVar("turn_cache", default=None)


def turn_cache_active() -> bool:
    return is_enabled("ENABLE_TURN_CACHE")


class TurnCache:
    """Per-turn cache keyed by request_id + lane + logical key.

    This cache is a performance-only optimization. Misses must always fall back
    to the normal compute path and must never change product semantics."""

    def __init__(self, *, request_id: str | None, lane: str = "") -> None:
        self._request_id = str(request_id or "")
        self._lane = str(lane or "")
        self._store: dict[str, Any] = {}
        self._stats: dict[str, int] = {"hits": 0, "misses": 0}

    @property
    def lane(self) -> str:
        return self._lane

    def set_lane(self, lane: str) -> None:
        self._lane = str(lane or "")

    def _full_key(self, key: str, *, lane: str | None = None) -> str:
        lane_part = str(lane or self._lane or "general")
        return f"{self._request_id}:{lane_part}:{key}"

    def get_or_compute(
        self,
        key: str,
        fn: Callable[[], T],
        *,
        lane: str | None = None,
    ) -> T:
        full_key = self._full_key(key, lane=lane)
        if full_key in self._store:
            self._stats["hits"] += 1
            return self._store[full_key]
        self._stats["misses"] += 1
        value = fn()
        self._store[full_key] = value
        return value

    def set(self, key: str, value: Any, *, lane: str | None = None) -> None:
        self._store[self._full_key(key, lane=lane)] = value

    def get(self, key: str, *, lane: str | None = None) -> Any | None:
        return self._store.get(self._full_key(key, lane=lane))

    def hits(self) -> dict[str, int]:
        return dict(self._stats)


def current_turn_cache() -> TurnCache | None:
    return _turn_cache_ctx.get()


def bind_turn_cache(cache: TurnCache | None) -> Token[TurnCache | None]:
    return _turn_cache_ctx.set(cache)


def reset_turn_cache(token: Token[TurnCache | None]) -> None:
    _turn_cache_ctx.reset(token)
