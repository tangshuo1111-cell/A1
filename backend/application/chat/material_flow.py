"""Material layer / scope trace — single resolver for response extra (Round 6)."""

from __future__ import annotations

from typing import Any

from application.chat.material_lifecycle import (
    material_state_from_legacy,
    resolve_trace_from_pending_item,
    trace_fields_for_state,
)

_LAYER_TEMPORARY = "temporary"
_LAYER_PENDING = "pending"
_LAYER_COMMITTED = "committed"

_SCOPE_SESSION = "session"
_SCOPE_PENDING = "pending"
_SCOPE_KNOWLEDGE = "knowledge"


def resolve_material_trace(
    *,
    bundle: Any | None = None,
    retrieved_chunks_count: int = 0,
    use_knowledge: bool = False,
    has_temporary_materials: bool = False,
) -> dict[str, Any]:
    """Map bundle + retrieval snapshot to unified material trace fields."""
    pending = getattr(bundle, "pending_item", None) if bundle is not None else None
    temps = list(getattr(bundle, "temporary_materials", []) or []) if bundle is not None else []

    if pending is not None:
        return resolve_trace_from_pending_item(
            pending,
            retrieved_chunks_count=retrieved_chunks_count,
            temporary_count=len(temps),
            use_knowledge=use_knowledge,
        )

    state = material_state_from_legacy(
        material_status=str(getattr(bundle, "v13_material_status", "") or "") if bundle is not None else "",
    )
    source_count = retrieved_chunks_count + len(temps)
    if has_temporary_materials:
        source_count = max(source_count, len(temps))

    trace = trace_fields_for_state(
        state,
        source_count=source_count,
        use_knowledge=use_knowledge,
    )
    if retrieved_chunks_count > 0 and trace["material_layer_used"] == _LAYER_TEMPORARY:
        trace = dict(trace)
        trace["material_scope"] = _SCOPE_KNOWLEDGE if use_knowledge else _SCOPE_SESSION
    return trace


def material_trace_from_bundle(bundle: Any, *, use_knowledge: bool = False) -> dict[str, Any]:
    chunks = list(getattr(bundle, "retrieved_chunks", []) or [])
    temps = list(getattr(bundle, "temporary_materials", []) or [])
    return resolve_material_trace(
        bundle=bundle,
        retrieved_chunks_count=len(chunks),
        use_knowledge=use_knowledge,
        has_temporary_materials=bool(temps),
    )


def material_trace_for_extra(
    *,
    bundle: Any | None = None,
    shared_prep: Any | None = None,
    lane: str = "general",
    use_knowledge: bool = False,
    executor_profile: str = "fast",
    approval_kind: str | None = None,
    has_fast_material: bool = False,
    pending_count: int = 0,
) -> dict[str, Any]:
    """Unified material trace for any turn exit (fast / complex / async / approval)."""
    if bundle is not None:
        return material_trace_from_bundle(bundle, use_knowledge=use_knowledge)

    if shared_prep is not None and getattr(shared_prep, "snapshot", None) is not None:
        return trace_fields_for_state(
            "prepared",
            source_count=int(shared_prep.snapshot.hits or 0),
            use_knowledge=use_knowledge or lane == "kb",
        )

    if approval_kind == "pending_commit":
        return trace_fields_for_state("pending_commit", source_count=max(pending_count, 1))

    if executor_profile == "async":
        return trace_fields_for_state("prepared", source_count=1 if has_fast_material else 0)

    if lane in {"video", "document", "web", "kb"} and has_fast_material:
        trace = trace_fields_for_state("prepared", source_count=1)
        if lane == "kb":
            trace = dict(trace)
            trace["material_scope"] = _SCOPE_KNOWLEDGE
        return trace

    return trace_fields_for_state("prepared", source_count=0)
