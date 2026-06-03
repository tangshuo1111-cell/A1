"""Pending lifecycle schema facade — agents import types/constants from here only."""

from __future__ import annotations

from rag.pending_schema import (
    PENDING_KIND_COMMITTED,
    PENDING_KIND_FAST_PENDING,
    PENDING_KIND_MATERIAL_PENDING,
    PENDING_KIND_NONE,
    PENDING_KIND_PARTIAL_PENDING,
    PENDING_KIND_PROCESSING_PENDING,
    SOURCE_TYPE_ASR_TRANSCRIPT,
    SOURCE_TYPE_DOCX,
    SOURCE_TYPE_LOCAL_VIDEO,
    SOURCE_TYPE_OCR_DOCUMENT,
    SOURCE_TYPE_PDF,
    SOURCE_TYPE_TEXT,
    SOURCE_TYPE_TEXT_FILE,
    SOURCE_TYPE_WEB_SEARCH,
    SOURCE_TYPE_WEB_URL,
    SOURCE_TYPE_WEB_VIDEO,
    SOURCE_TYPE_XLSX,
    STATUS_COMMITTED,
    STATUS_DISCARDED,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_TEMPORARY,
    PendingKnowledgeItem,
    SourcePayload,
    derive_pending_kind,
)

__all__ = [
    "PENDING_KIND_COMMITTED",
    "PENDING_KIND_FAST_PENDING",
    "PENDING_KIND_MATERIAL_PENDING",
    "PENDING_KIND_NONE",
    "PENDING_KIND_PARTIAL_PENDING",
    "PENDING_KIND_PROCESSING_PENDING",
    "derive_pending_kind",
    "SOURCE_TYPE_ASR_TRANSCRIPT",
    "SOURCE_TYPE_DOCX",
    "SOURCE_TYPE_LOCAL_VIDEO",
    "SOURCE_TYPE_OCR_DOCUMENT",
    "SOURCE_TYPE_PDF",
    "SOURCE_TYPE_TEXT",
    "SOURCE_TYPE_TEXT_FILE",
    "SOURCE_TYPE_WEB_SEARCH",
    "SOURCE_TYPE_WEB_URL",
    "SOURCE_TYPE_WEB_VIDEO",
    "SOURCE_TYPE_XLSX",
    "STATUS_COMMITTED",
    "STATUS_DISCARDED",
    "STATUS_FAILED",
    "STATUS_PENDING",
    "STATUS_TEMPORARY",
    "PendingKnowledgeItem",
    "SourcePayload",
]


def resolve_pending_kind(item: PendingKnowledgeItem) -> str:
    """Return canonical pending_kind for a store record (S10a)."""
    kind = str(getattr(item, "pending_kind", "") or "").strip()
    if kind:
        return kind
    return derive_pending_kind(
        extract_status=item.extract_status,
        commit_status=item.commit_status,
        error_code=item.error_code,
    )
