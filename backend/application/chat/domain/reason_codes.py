"""Canonical reason codes for profile / path transitions."""

from __future__ import annotations

# Ingress
INGRESS_FAST_KB = "INGRESS_FAST_KB"
INGRESS_FAST_WEB = "INGRESS_FAST_WEB"
INGRESS_FAST_VIDEO = "INGRESS_FAST_VIDEO"
INGRESS_FAST_DOCUMENT = "INGRESS_FAST_DOCUMENT"
INGRESS_FAST_GENERAL = "INGRESS_FAST_GENERAL"
INGRESS_COMPLEX = "INGRESS_COMPLEX"
INGRESS_ASYNC = "INGRESS_ASYNC"

# Gates / arbitration
PENDING_BLOCKS_FAST = "PENDING_BLOCKS_FAST"
APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
FAST_LANE_REJECTED = "FAST_LANE_REJECTED"
QUALITY_REQUIRES_COMPLEX = "QUALITY_REQUIRES_COMPLEX"
BUDGET_ASYNC_FALLBACK = "BUDGET_ASYNC_FALLBACK"
CAPABILITY_ASYNC_FALLBACK = "CAPABILITY_ASYNC_FALLBACK"
MULTI_SOURCE_REQUIRES_COMPLEX = "MULTI_SOURCE_REQUIRES_COMPLEX"
ARBITRATOR_INACTIVE = "ARBITRATOR_INACTIVE"

_ARBITRATOR_DETAIL_TO_CODE: dict[str, str] = {
    "session_pending_active": PENDING_BLOCKS_FAST,
    "budget_reserved_exhausted": BUDGET_ASYNC_FALLBACK,
    "capability_demote_to_async": CAPABILITY_ASYNC_FALLBACK,
    "multi_source_compare": MULTI_SOURCE_REQUIRES_COMPLEX,
    "ingress_mode": INGRESS_FAST_GENERAL,
    "arbitrator_inactive": ARBITRATOR_INACTIVE,
}


def canonical_code(detail_reason: str, *, lane: str = "general", ingress_mode: str = "fast") -> str:
    """Map legacy detail reason + lane to a canonical code."""
    if detail_reason in _ARBITRATOR_DETAIL_TO_CODE:
        code = _ARBITRATOR_DETAIL_TO_CODE[detail_reason]
        if detail_reason == "ingress_mode":
            if ingress_mode == "async":
                return INGRESS_ASYNC
            if ingress_mode == "complex":
                return INGRESS_COMPLEX
            if lane == "kb":
                return INGRESS_FAST_KB
            if lane == "web":
                return INGRESS_FAST_WEB
            if lane == "video":
                return INGRESS_FAST_VIDEO
            if lane == "document":
                return INGRESS_FAST_DOCUMENT
            return INGRESS_FAST_GENERAL
        return code
    if detail_reason == "quality_gate_upgrade":
        return QUALITY_REQUIRES_COMPLEX
    if detail_reason == "fast_lane_blocked":
        return FAST_LANE_REJECTED
    return detail_reason
