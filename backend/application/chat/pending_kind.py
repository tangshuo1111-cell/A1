"""PendingKind — stable frontend contract (§5.4)."""
from __future__ import annotations

from enum import StrEnum
from typing import Any


class PendingKind(StrEnum):
    NONE = "none"
    FAST_PENDING = "fast_pending"
    PROCESSING_PENDING = "processing_pending"
    MATERIAL_PENDING = "material_pending"
    PARTIAL_PENDING = "partial_pending"
    COMMITTED = "committed"


def resolve_pending_kind_for_bundle(
    *,
    bundle: Any,
    history_snapshot: Any,
    session_pending_kind: PendingKind = PendingKind.NONE,
) -> PendingKind | None:
    """Resolve pending kind signal from bundle/session (not final HTTP write)."""
    from application.chat.complex_pending_mapping import (
        complex_pending_kind_active,
        resolve_bundle_pending_kind,
    )
    from application.chat.decision_arbitrator import resolve_session_pending_kind

    pending_item = getattr(bundle, "pending_item", None)
    if pending_item is not None:
        from services.capabilities.knowledge.pending_service import (
            resolve_pending_kind as resolve_item_kind,
        )

        raw = resolve_item_kind(pending_item)
        try:
            return PendingKind(str(raw))
        except ValueError:
            return PendingKind.MATERIAL_PENDING
    if not complex_pending_kind_active():
        if session_pending_kind != PendingKind.NONE:
            return session_pending_kind
        session_only = resolve_session_pending_kind(
            pending_video=getattr(history_snapshot, "pending_video_text", None),
            prev_video=getattr(history_snapshot, "prev_video", None),
        )
        return session_only if session_only != PendingKind.NONE else None
    session_pending = (
        session_pending_kind
        if session_pending_kind != PendingKind.NONE
        else resolve_session_pending_kind(
            pending_video=getattr(history_snapshot, "pending_video_text", None),
            prev_video=getattr(history_snapshot, "prev_video", None),
        )
    )
    resolved = resolve_bundle_pending_kind(
        bundle=bundle,
        session_pending=session_pending,
    )
    return resolved if resolved != PendingKind.NONE else None
