"""Round 7 — session + pending persistence ports and backends."""

from __future__ import annotations

from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_storage_ports_exist() -> None:
    assert (PROJECT_ROOT / "backend" / "storage" / "ports" / "session_store.py").is_file()
    assert (PROJECT_ROOT / "backend" / "storage" / "ports" / "pending_store.py").is_file()
    assert (PROJECT_ROOT / "backend" / "storage" / "store_factory.py").is_file()


def test_session_store_facade_uses_factory() -> None:
    text = (PROJECT_ROOT / "backend" / "services" / "session_store.py").read_text(encoding="utf-8")
    assert "store_factory" in text
    assert "MemoryChatSessionStore" in text


def test_pending_store_facade_uses_factory() -> None:
    assert not (PROJECT_ROOT / "backend" / "rag" / "pending_store.py").exists()
    text = (PROJECT_ROOT / "backend" / "services" / "pending_store.py").read_text(encoding="utf-8")
    assert "create_pending_store" in text
    assert "get_pending_store" in text


def test_services_pending_store_is_canonical_facade() -> None:
    text = (PROJECT_ROOT / "backend" / "services" / "pending_store.py").read_text(encoding="utf-8")
    assert "get_pending_store" in text
    assert "PendingStorePort" in text
    assert "reset_stores_for_tests" in text


def test_pg_pool_defines_session_and_pending_tables() -> None:
    text = (PROJECT_ROOT / "backend" / "storage" / "pg_pool.py").read_text(encoding="utf-8")
    assert "agno_session_state" in text
    assert "agno_pending_items" in text


def test_lifespan_validates_store_backend() -> None:
    text = (PROJECT_ROOT / "backend" / "api" / "lifespan.py").read_text(encoding="utf-8")
    assert "validate_startup_config" in text


def test_agno_service_persists_session_after_turn() -> None:
    text = (PROJECT_ROOT / "backend" / "services" / "agno_chat_service.py").read_text(encoding="utf-8")
    assert "ensure_session" in text
    assert "persist_session" in text


def test_default_store_backend_is_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("STORE_BACKEND", raising=False)
    from config.settings import Settings

    s = Settings()
    assert s.store_backend == "memory"


def test_prod_memory_store_backend_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    from config.settings import settings
    from storage.validate_store_backend import validate_store_backend

    monkeypatch.setattr(settings, "app_env", "prod")
    monkeypatch.setattr(settings, "store_backend", "memory")
    with pytest.raises(RuntimeError, match="APP_ENV=prod forbids STORE_BACKEND=memory"):
        validate_store_backend()


def test_pending_item_dict_roundtrip() -> None:
    from rag.pending_schema import (
        SOURCE_TYPE_TEXT,
        STATUS_PENDING,
        PendingKnowledgeItem,
        pending_item_from_dict,
        pending_item_to_dict,
    )

    item = PendingKnowledgeItem(
        pending_id="pid-1",
        session_id="sess-1",
        source_type=SOURCE_TYPE_TEXT,
        title="t",
        raw_source="",
        text="body",
        preview_text="body",
        metadata={"k": 1},
        parser_name="plain",
        extract_status="ok",
        error_code="",
        created_at="2026-01-01T00:00:00+00:00",
        commit_status=STATUS_PENDING,
        pending_kind="material_pending",
    )
    restored = pending_item_from_dict(pending_item_to_dict(item))
    assert restored.pending_id == item.pending_id
    assert restored.text == item.text
    assert restored.metadata == item.metadata


def test_memory_pending_store_behavior() -> None:
    from rag.pending_schema import SOURCE_TYPE_TEXT, STATUS_PENDING, PendingKnowledgeItem
    from storage.memory_pending_store import MemoryPendingStore

    store = MemoryPendingStore()
    item = PendingKnowledgeItem(
        pending_id="p1",
        session_id="s1",
        source_type=SOURCE_TYPE_TEXT,
        title="",
        raw_source="",
        text="x",
        preview_text="x",
        metadata={},
        parser_name="plain",
        extract_status="ok",
        error_code="",
        created_at="t",
        commit_status=STATUS_PENDING,
    )
    store.add(item)
    assert store.get_recent("s1") is item
    assert store.mark_committed("p1", committed_source_id="kb:1", chunk_count=2)
    assert store.get("p1") is not None
    assert store.get("p1").is_committed
