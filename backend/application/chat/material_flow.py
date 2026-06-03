"""Material layer / scope trace — single resolver for response extra (doc §2)."""

from __future__ import annotations

from typing import Any

from rag.pending_schema import (
    STATUS_COMMITTED,
    STATUS_PENDING,
    STATUS_TEMPORARY,
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
    layer = _LAYER_TEMPORARY
    scope = _SCOPE_SESSION
    source_count = 0

    pending = getattr(bundle, "pending_item", None) if bundle is not None else None
    if pending is not None:
        source_count += 1
        commit_status = str(getattr(pending, "commit_status", "") or "")
        material_status = str(getattr(pending, "material_status", "") or getattr(bundle, "v13_material_status", "") or "")
        if commit_status == STATUS_COMMITTED or material_status == STATUS_COMMITTED:
            layer = _LAYER_COMMITTED
            scope = _SCOPE_KNOWLEDGE
        elif commit_status == STATUS_PENDING or material_status == STATUS_PENDING:
            layer = _LAYER_PENDING
            scope = _SCOPE_PENDING
        else:
            layer = _LAYER_TEMPORARY
            scope = _SCOPE_PENDING if material_status else _SCOPE_SESSION

    temps = list(getattr(bundle, "temporary_materials", []) or []) if bundle is not None else []
    if temps:
        source_count += len(temps)
        if layer == _LAYER_TEMPORARY and not pending:
            layer = _LAYER_TEMPORARY
            scope = _SCOPE_SESSION

    if retrieved_chunks_count > 0:
        source_count += retrieved_chunks_count
        if layer == _LAYER_TEMPORARY and not pending:
            layer = _LAYER_TEMPORARY
            scope = _SCOPE_KNOWLEDGE if use_knowledge else _SCOPE_SESSION

    if has_temporary_materials and layer == _LAYER_TEMPORARY:
        scope = _SCOPE_SESSION

    v13_status = str(getattr(bundle, "v13_material_status", "") or "") if bundle is not None else ""
    if v13_status == STATUS_TEMPORARY and not pending:
        layer = _LAYER_TEMPORARY

    return {
        "material_layer_used": layer,
        "material_scope": scope,
        "material_source_count": max(source_count, retrieved_chunks_count, len(temps)),
    }


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
        return resolve_material_trace(
            retrieved_chunks_count=int(shared_prep.snapshot.hits or 0),
            use_knowledge=use_knowledge or lane == "kb",
        )

    if approval_kind == "pending_commit":
        return {
            "material_layer_used": _LAYER_PENDING,
            "material_scope": _SCOPE_PENDING,
            "material_source_count": max(pending_count, 1 if pending_count else 0),
        }

    if executor_profile == "async":
        return {
            "material_layer_used": _LAYER_TEMPORARY,
            "material_scope": _SCOPE_SESSION,
            "material_source_count": 1 if has_fast_material else 0,
        }

    if lane in {"video", "document", "web", "kb"} and has_fast_material:
        scope = _SCOPE_KNOWLEDGE if lane == "kb" else _SCOPE_SESSION
        return {
            "material_layer_used": _LAYER_TEMPORARY,
            "material_scope": scope,
            "material_source_count": 1,
        }

    return {
        "material_layer_used": _LAYER_TEMPORARY,
        "material_scope": _SCOPE_SESSION,
        "material_source_count": 0,
    }
