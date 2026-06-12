"""PostgreSQL-backed chat session store."""

from __future__ import annotations

import json
import logging
from collections import deque
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

from domain.session_types import PendingVideoText, PrevVideoRef
from storage.memory_chat_session_store import MemoryChatSessionStore
from storage.pg_pool import get_pool

logger = logging.getLogger("light_maqa")


def _video_ref_to_dict(ref: PrevVideoRef | None) -> dict[str, Any] | None:
    if ref is None:
        return None
    return asdict(ref)


def _video_ref_from_dict(data: dict[str, Any] | None) -> PrevVideoRef | None:
    if not data:
        return None
    return PrevVideoRef(
        source_id=str(data.get("source_id") or ""),
        basename=data.get("basename"),
        path=data.get("path"),
    )


def _pending_video_to_dict(pv: PendingVideoText | None) -> dict[str, Any] | None:
    if pv is None:
        return None
    return asdict(pv)


def _pending_video_from_dict(data: dict[str, Any] | None) -> PendingVideoText | None:
    if not data:
        return None
    return PendingVideoText(
        text=str(data.get("text") or ""),
        title=str(data.get("title") or ""),
        source_url=str(data.get("source_url") or ""),
        source_basename=str(data.get("source_basename") or ""),
        duration_sec=float(data.get("duration_sec") or 0.0),
        text_source=str(data.get("text_source") or ""),
        subtitle_lang=data.get("subtitle_lang"),
        asr_provider=data.get("asr_provider"),
    )


class PgChatSessionStore(MemoryChatSessionStore):
    """Memory cache with PG durability; orchestrator may mutate dicts in place."""

    def __init__(self) -> None:
        super().__init__()
        self._loaded_keys: set[str] = set()

    def ensure_session(self, key: str) -> None:
        if key in self._loaded_keys:
            return
        with self._lock:
            if key in self._loaded_keys:
                return
            self._load_from_pg(key)
            self._loaded_keys.add(key)

    def get_history(self, key: str, max_pairs: int) -> deque[tuple[str, str]]:
        self.ensure_session(key)
        return super().get_history(key, max_pairs)

    def get_prev_video(self, key: str) -> PrevVideoRef | None:
        self.ensure_session(key)
        return super().get_prev_video(key)

    def get_pending_video(self, key: str) -> PendingVideoText | None:
        self.ensure_session(key)
        return super().get_pending_video(key)

    def persist_session(self, key: str) -> None:
        self.ensure_session(key)
        with self._lock:
            history = list(self._histories.get(key, []))
            prev = self._prev_video.get(key)
            pending = self._pending_video.get(key)
        ts = datetime.now(tz=UTC).isoformat()
        try:
            pool = get_pool()
            with pool.connection() as conn, conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO agno_session_state (
                        session_key, history_json, prev_video_json, pending_video_json, updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (session_key) DO UPDATE SET
                        history_json = EXCLUDED.history_json,
                        prev_video_json = EXCLUDED.prev_video_json,
                        pending_video_json = EXCLUDED.pending_video_json,
                        updated_at = EXCLUDED.updated_at;
                    """,
                    (
                        key,
                        json.dumps(history, ensure_ascii=False),
                        json.dumps(_video_ref_to_dict(prev), ensure_ascii=False),
                        json.dumps(_pending_video_to_dict(pending), ensure_ascii=False),
                        ts,
                    ),
                )
            conn.commit()
        except Exception:  # noqa: BLE001
            logger.exception("persist_session failed key=%s", key)

    def clear_all(self) -> None:
        super().clear_all()
        self._loaded_keys.clear()
        try:
            pool = get_pool()
            with pool.connection() as conn, conn.cursor() as cur:
                cur.execute("DELETE FROM agno_session_state;")
            conn.commit()
        except Exception:  # noqa: BLE001
            logger.exception("clear_all agno_session_state failed")

    def _load_from_pg(self, key: str) -> None:
        try:
            pool = get_pool()
            with pool.connection() as conn, conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT history_json, prev_video_json, pending_video_json
                    FROM agno_session_state
                    WHERE session_key = %s;
                    """,
                    (key,),
                )
                row = cur.fetchone()
        except Exception:  # noqa: BLE001
            logger.exception("load session failed key=%s", key)
            return
        if not row:
            return
        history_raw, prev_raw, pending_raw = row
        if history_raw:
            pairs = json.loads(history_raw)
            if isinstance(pairs, list):
                dq: deque[tuple[str, str]] = deque(maxlen=10_000)
                for pair in pairs:
                    if isinstance(pair, (list, tuple)) and len(pair) == 2:
                        dq.append((str(pair[0]), str(pair[1])))
                if dq:
                    self._histories[key] = dq
        if prev_raw:
            self._prev_video[key] = _video_ref_from_dict(json.loads(prev_raw))
        if pending_raw:
            self._pending_video[key] = _pending_video_from_dict(json.loads(pending_raw))
