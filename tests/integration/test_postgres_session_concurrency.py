"""PostgreSQL session store — concurrent access smoke (R20).

Documents current semantics: concurrent ``persist_session`` without row-level merge
is last-write-wins; test asserts no crash and at least one durable append.
"""

from __future__ import annotations

import threading

from tests._support.pg_fixtures import pg_required_marks

pytestmark = pg_required_marks()


def test_pg_chat_session_concurrent_persist_is_last_write_wins(pg_settings) -> None:  # noqa: ARG001
    from storage.pg_chat_session_store import PgChatSessionStore

    key = "pg-concurrent-session"
    store = PgChatSessionStore()
    store.clear_all()

    errors: list[str] = []

    def _writer(tag: str) -> None:
        try:
            local = PgChatSessionStore()
            history = local.get_history(key, 50)
            history.append((f"user-{tag}", f"msg-{tag}"))
            local.persist_session(key)
        except Exception as exc:  # pragma: no cover - surfaced via errors list
            errors.append(f"{tag}:{exc}")

    threads = [threading.Thread(target=_writer, args=(str(i),)) for i in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert not errors, errors

    reader = PgChatSessionStore()
    restored = list(reader.get_history(key, 50))
    assert 1 <= len(restored) <= 8
    assert restored[0][0].startswith("user-")

    reader.clear_all()


def test_pg_chat_session_restore_after_concurrent_burst(pg_settings) -> None:  # noqa: ARG001
    """After a concurrent burst, a fresh reader can append and read back reliably."""
    from storage.pg_chat_session_store import PgChatSessionStore

    key = "pg-restore-after-burst"
    store = PgChatSessionStore()
    store.clear_all()

    errors: list[str] = []

    def _writer(tag: str) -> None:
        try:
            local = PgChatSessionStore()
            history = local.get_history(key, 50)
            history.append((f"burst-{tag}", f"payload-{tag}"))
            local.persist_session(key)
        except Exception as exc:  # pragma: no cover
            errors.append(f"{tag}:{exc}")

    threads = [threading.Thread(target=_writer, args=(str(i),)) for i in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert not errors

    recovery = PgChatSessionStore()
    history = recovery.get_history(key, 50)
    history.append(("user-recovery", "after-burst"))
    recovery.persist_session(key)

    restored = list(recovery.get_history(key, 50))
    assert any(role == "user-recovery" and content == "after-burst" for role, content in restored)

    recovery.clear_all()
