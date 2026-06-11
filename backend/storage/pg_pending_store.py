"""PostgreSQL-backed pending knowledge store (Round 7)."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from rag.pending_schema import pending_item_from_dict, pending_item_to_dict
from storage.memory_pending_store import MemoryPendingStore
from storage.pg_pool import get_pool

logger = logging.getLogger("light_maqa")


class PgPendingStore(MemoryPendingStore):
    """Memory cache with per-mutation PG sync."""

    def __init__(self) -> None:
        super().__init__()
        self._loaded_sessions: set[str] = set()

    def _ensure_session_loaded(self, session_id: str) -> None:
        sid = session_id or "__default__"
        if sid in self._loaded_sessions:
            return
        with self._lock:
            if sid in self._loaded_sessions:
                return
            self._load_session_from_pg(sid)
            self._loaded_sessions.add(sid)

    def add(self, item) -> None:
        sid = item.session_id or "__default__"
        with self._lock:
            if sid not in self._loaded_sessions:
                self._load_session_from_pg(sid)
                self._loaded_sessions.add(sid)
            self._data.setdefault(sid, []).append(item)
            self._upsert_item_unlocked(item)

    def mark_committed(
        self,
        pending_id: str,
        *,
        committed_source_id: str,
        chunk_count: int,
    ) -> bool:
        with self._lock:
            found = super().mark_committed(
                pending_id,
                committed_source_id=committed_source_id,
                chunk_count=chunk_count,
            )
            if not found:
                return False
            for items in self._data.values():
                for item in items:
                    if item.pending_id == pending_id:
                        self._upsert_item_unlocked(item)
                        return True
        return False

    def discard(self, pending_id: str) -> bool:
        with self._lock:
            found = super().discard(pending_id)
            if not found:
                return False
            for items in self._data.values():
                for item in items:
                    if item.pending_id == pending_id:
                        self._upsert_item_unlocked(item)
                        return True
        return False

    def list_for_session(
        self,
        session_id: str,
        *,
        only_committable: bool = False,
    ) -> list:
        self._ensure_session_loaded(session_id)
        return super().list_for_session(session_id, only_committable=only_committable)

    def get_recent(self, session_id: str, *, only_committable: bool = True):
        self._ensure_session_loaded(session_id)
        return super().get_recent(session_id, only_committable=only_committable)

    def count_committable(self, session_id: str) -> int:
        self._ensure_session_loaded(session_id)
        return super().count_committable(session_id)

    def discard_session(self, session_id: str) -> None:
        sid = session_id or "__default__"
        with self._lock:
            super().discard_session(session_id)
            self._loaded_sessions.discard(sid)
            self._delete_session_from_pg(sid)

    def clear_all(self) -> None:
        with self._lock:
            super().clear_all()
            self._loaded_sessions.clear()
            self._truncate_pg()

    def _upsert_item_unlocked(self, item) -> None:
        ts = datetime.now(tz=UTC).isoformat()
        payload = json.dumps(pending_item_to_dict(item), ensure_ascii=False)
        sid = item.session_id or "__default__"
        try:
            pool = get_pool()
            with pool.connection() as conn, conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO agno_pending_items (
                        pending_id, session_id, payload_json, created_at, updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (pending_id) DO UPDATE SET
                        session_id = EXCLUDED.session_id,
                        payload_json = EXCLUDED.payload_json,
                        updated_at = EXCLUDED.updated_at;
                    """,
                    (item.pending_id, sid, payload, item.created_at or ts, ts),
                )
            conn.commit()
        except Exception:  # noqa: BLE001
            logger.exception("pending upsert failed id=%s", item.pending_id)

    def _load_session_from_pg(self, sid: str) -> None:
        try:
            pool = get_pool()
            with pool.connection() as conn, conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT payload_json
                    FROM agno_pending_items
                    WHERE session_id = %s
                    ORDER BY created_at ASC;
                    """,
                    (sid,),
                )
                rows = cur.fetchall()
        except Exception:  # noqa: BLE001
            logger.exception("pending load failed session=%s", sid)
            return
        items = []
        for (payload_raw,) in rows:
            if not payload_raw:
                continue
            try:
                items.append(pending_item_from_dict(json.loads(payload_raw)))
            except Exception:  # noqa: BLE001
                logger.exception("pending deserialize failed session=%s", sid)
        if items:
            self._data[sid] = items

    def _delete_session_from_pg(self, sid: str) -> None:
        try:
            pool = get_pool()
            with pool.connection() as conn, conn.cursor() as cur:
                cur.execute("DELETE FROM agno_pending_items WHERE session_id = %s;", (sid,))
            conn.commit()
        except Exception:  # noqa: BLE001
            logger.exception("pending delete session failed session=%s", sid)

    def _truncate_pg(self) -> None:
        try:
            pool = get_pool()
            with pool.connection() as conn, conn.cursor() as cur:
                cur.execute("DELETE FROM agno_pending_items;")
            conn.commit()
        except Exception:  # noqa: BLE001
            logger.exception("pending truncate failed")
