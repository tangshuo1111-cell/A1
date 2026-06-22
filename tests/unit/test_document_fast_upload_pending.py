"""Upload + document_fast registers pending for later commit (KI-V1-004 fix)."""

from __future__ import annotations

from application.chat.executors.fast_lanes.document_fast_impl import _register_upload_pending_extra
from services.pending_store import reset_pending_store_for_tests


def test_register_upload_pending_extra_ok() -> None:
    reset_pending_store_for_tests()
    sid = "unit-doc-fast-pending"
    extra = _register_upload_pending_extra(
        session_id=sid,
        file_path="flow_brief.md",
        file_content="# Title\n\nBody with enough content for prepare.\n",
    )
    assert extra.get("v13_material_status") == "pending"
    assert extra.get("pending_source_id")
    assert extra.get("exit_signal_pending_kind") == "material_pending"

    from services.capabilities.knowledge import pending_ingestion_service

    items = pending_ingestion_service.list_pending(sid, only_committable=True)
    assert len(items) == 1
    reset_pending_store_for_tests()
