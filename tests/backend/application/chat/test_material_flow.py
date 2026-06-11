"""Tests for material_flow trace resolver."""
from __future__ import annotations

from types import SimpleNamespace

from application.chat.material_flow import material_trace_from_bundle, resolve_material_trace


def test_resolve_material_trace_kb_retrieval():
    trace = resolve_material_trace(retrieved_chunks_count=3, use_knowledge=True)
    assert trace["material_layer_used"] == "temporary"
    assert trace["material_scope"] == "knowledge"
    assert trace["material_source_count"] == 3


def test_material_trace_from_pending_bundle():
    bundle = SimpleNamespace(
        pending_item=SimpleNamespace(
            commit_status="pending",
            material_status="pending",
            source_type="text",
            extract_status="ok",
            pending_id="p",
            session_id="s",
            title="",
            preview_text="",
            metadata={},
        ),
        retrieved_chunks=[],
        temporary_materials=[],
    )
    trace = material_trace_from_bundle(bundle)
    assert trace["material_layer_used"] == "pending"
    assert trace["material_scope"] == "pending"


def test_material_trace_from_committed_pending():
    bundle = SimpleNamespace(
        pending_item=SimpleNamespace(
            commit_status="committed",
            material_status="committed",
            source_type="text",
            extract_status="ok",
            pending_id="p",
            session_id="s",
            title="",
            preview_text="",
            committed_source_id="kb:1",
            committed_chunk_count=1,
            metadata={},
        ),
        retrieved_chunks=[],
        temporary_materials=[],
    )
    trace = material_trace_from_bundle(bundle)
    assert trace["material_layer_used"] == "committed"
    assert trace["material_scope"] == "knowledge"


def test_material_trace_for_async_and_approval():
    from application.chat.material_flow import material_trace_for_extra

    async_trace = material_trace_for_extra(lane="video", executor_profile="async", has_fast_material=True)
    assert async_trace["material_layer_used"] == "temporary"
    assert async_trace["material_scope"] == "session"

    blocked = material_trace_for_extra(approval_kind="pending_commit", pending_count=0, executor_profile="blocked")
    assert blocked["material_layer_used"] == "pending"
    assert blocked["material_scope"] == "pending"
