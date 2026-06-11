"""Material lifecycle adapters — map store/bundle shapes to chat_contracts (Round 6)."""

from __future__ import annotations

from typing import Any

from application.chat.chat_contracts import (
    CommittedMaterial,
    MaterialLayer,
    MaterialScope,
    MaterialSource,
    MaterialState,
    PendingMaterial,
    PreparedMaterial,
)

_LEGACY_COMMITTED = frozenset({"committed"})
_LEGACY_PENDING = frozenset({"pending"})
_LEGACY_TEMPORARY = frozenset({"temporary", "prepared"})
_LEGACY_FAILED = frozenset({"failed", "parse_failed", "empty_content"})
_LEGACY_DISCARDED = frozenset({"discarded"})

_SOURCE_MAP: dict[str, MaterialSource] = {
    "text": "text",
    "text_file": "upload",
    "web_url": "web",
    "web_search": "web",
    "local_video": "local_video",
    "web_video": "web_video",
    "docx": "document",
    "xlsx": "document",
    "pdf": "document",
    "ocr_document": "document",
    "asr_transcript": "local_video",
}


def normalize_material_source(source_type: str) -> MaterialSource:
    key = str(source_type or "").strip().lower()
    return _SOURCE_MAP.get(key, "text")


def material_state_from_legacy(
    *,
    commit_status: str = "",
    material_status: str = "",
    extract_status: str = "",
    error_code: str = "",
) -> MaterialState:
    commit = str(commit_status or "").strip().lower()
    material = str(material_status or "").strip().lower()
    extract = str(extract_status or "").strip().lower()
    err = str(error_code or "").strip()
    if commit in _LEGACY_COMMITTED or material in _LEGACY_COMMITTED:
        return "committed"
    if commit in _LEGACY_DISCARDED or material in _LEGACY_DISCARDED:
        return "discarded"
    if err or extract in _LEGACY_FAILED or material in _LEGACY_FAILED:
        return "failed"
    if commit in _LEGACY_PENDING or material in _LEGACY_PENDING:
        return "pending_commit"
    if material in _LEGACY_TEMPORARY:
        return "prepared"
    if extract == "ok" and not err:
        return "pending_commit"
    return "prepared"


def layer_and_scope_for_state(state: MaterialState) -> tuple[MaterialLayer, MaterialScope]:
    if state == "committed":
        return "committed", "knowledge"
    if state == "pending_commit":
        return "pending", "pending"
    if state == "failed":
        return "temporary", "session"
    if state == "discarded":
        return "temporary", "session"
    return "temporary", "session"


def trace_fields_for_state(
    state: MaterialState,
    *,
    source_count: int = 0,
    use_knowledge: bool = False,
    has_pending_scope: bool = False,
) -> dict[str, Any]:
    layer, scope = layer_and_scope_for_state(state)
    if state == "prepared" and use_knowledge and source_count > 0 and not has_pending_scope:
        scope = "knowledge"
    return {
        "material_layer_used": layer,
        "material_scope": scope,
        "material_source_count": max(source_count, 0),
        "material_state": state,
    }


def pending_item_to_material(item: Any) -> PendingMaterial | CommittedMaterial | PreparedMaterial:
    state = material_state_from_legacy(
        commit_status=str(getattr(item, "commit_status", "") or ""),
        material_status=str(getattr(item, "material_status", "") or ""),
        extract_status=str(getattr(item, "extract_status", "") or ""),
        error_code=str(getattr(item, "error_code", "") or ""),
    )
    source = normalize_material_source(str(getattr(item, "source_type", "") or ""))
    base = {
        "pending_id": str(getattr(item, "pending_id", "") or ""),
        "session_id": str(getattr(item, "session_id", "") or ""),
        "source": source,
        "title": str(getattr(item, "title", "") or ""),
        "preview_text": str(getattr(item, "preview_text", "") or ""),
    }
    if state == "committed":
        meta = getattr(item, "metadata", {}) or {}
        return CommittedMaterial(
            pending_id=base["pending_id"],
            source_id=str(getattr(item, "committed_source_id", "") or meta.get("source_id", "") or ""),
            session_id=base["session_id"],
            source=source,
            chunk_count=int(getattr(item, "committed_chunk_count", 0) or 0),
            title=base["title"],
            state="committed",
            success=True,
        )
    if state == "pending_commit":
        return PendingMaterial(
            pending_id=base["pending_id"],
            session_id=base["session_id"],
            source=source,
            title=base["title"],
            preview_text=base["preview_text"],
            state="pending_commit",
            error_code=str(getattr(item, "error_code", "") or ""),
        )
    prep_state: MaterialState = state if state in ("prepared", "failed", "discarded") else "prepared"
    return PreparedMaterial(
        pending_id=base["pending_id"],
        session_id=base["session_id"],
        source=source,
        title=base["title"],
        preview_text=base["preview_text"],
        state=prep_state,
    )


def committed_material_from_result(result: Any, *, session_id: str = "") -> CommittedMaterial:
    ok = bool(getattr(result, "success", False))
    state: MaterialState = "committed" if ok else "failed"
    return CommittedMaterial(
        pending_id=str(getattr(result, "pending_id", "") or ""),
        source_id=str(getattr(result, "source_id", "") or ""),
        session_id=session_id,
        source=normalize_material_source(str(getattr(result, "source_type", "") or "")),
        chunk_count=int(getattr(result, "chunk_count", 0) or 0),
        title=str(getattr(result, "title", "") or ""),
        state=state,
        success=ok,
        error_code=str(getattr(result, "error_code", "") or ""),
    )


def resolve_trace_from_pending_item(
    item: Any,
    *,
    retrieved_chunks_count: int = 0,
    temporary_count: int = 0,
    use_knowledge: bool = False,
) -> dict[str, Any]:
    material = pending_item_to_material(item)
    state = material.state
    source_count = 1 + retrieved_chunks_count + temporary_count
    return trace_fields_for_state(
        state,
        source_count=source_count,
        use_knowledge=use_knowledge,
        has_pending_scope=state == "pending_commit",
    )
