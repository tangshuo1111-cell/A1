"""Agent-layer re-export of neutral session types (canonical: ``domain.session_types``)."""

from __future__ import annotations

from domain.session_types import (
    PendingVideoText,
    PrevVideoRef,
    SessionHistorySnapshot,
    looks_like_followup_reference,
)

__all__ = [
    "PendingVideoText",
    "PrevVideoRef",
    "SessionHistorySnapshot",
    "looks_like_followup_reference",
]
