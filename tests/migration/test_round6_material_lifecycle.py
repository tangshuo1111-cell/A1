"""Round 6 — unified material lifecycle contracts."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_material_contract_types_exist() -> None:
    from application.chat.chat_contracts import CommittedMaterial, PendingMaterial, PreparedMaterial

    assert PreparedMaterial(pending_id="p1", session_id="s1", source="text").state == "prepared"
    assert PendingMaterial(pending_id="p1", session_id="s1", source="web").state == "pending_commit"
    assert CommittedMaterial(
        pending_id="p1", source_id="kb:1", session_id="s1", source="document", chunk_count=2
    ).state == "committed"


def test_material_flow_no_direct_rag_import() -> None:
    text = (PROJECT_ROOT / "backend" / "application" / "chat" / "material_flow.py").read_text(encoding="utf-8")
    assert "from rag." not in text
    assert "import rag." not in text


def test_prepare_pending_commit_state_mapping() -> None:
    from application.chat.material_lifecycle import pending_item_to_material

    pending = pending_item_to_material(
        SimpleNamespace(
            pending_id="id-1",
            session_id="sess",
            source_type="web_url",
            title="t",
            preview_text="preview",
            commit_status="pending",
            material_status="pending",
            extract_status="ok",
            error_code="",
            metadata={},
        )
    )
    assert pending.state == "pending_commit"
    assert pending.source == "web"

    committed = pending_item_to_material(
        SimpleNamespace(
            pending_id="id-2",
            session_id="sess",
            source_type="pdf",
            title="doc",
            preview_text="",
            commit_status="committed",
            material_status="committed",
            extract_status="ok",
            committed_source_id="kb:doc",
            committed_chunk_count=3,
            metadata={"source_id": "kb:doc"},
        )
    )
    assert committed.state == "committed"
    assert committed.source == "document"
    assert committed.chunk_count == 3


def test_material_trace_includes_material_state() -> None:
    from application.chat.material_flow import material_trace_from_bundle

    bundle = SimpleNamespace(
        pending_item=SimpleNamespace(
            pending_id="x",
            session_id="s",
            source_type="text",
            title="",
            preview_text="",
            commit_status="pending",
            material_status="pending",
            extract_status="ok",
            error_code="",
            metadata={},
        ),
        retrieved_chunks=[],
        temporary_materials=[],
    )
    trace = material_trace_from_bundle(bundle)
    assert trace["material_layer_used"] == "pending"
    assert trace["material_state"] == "pending_commit"
