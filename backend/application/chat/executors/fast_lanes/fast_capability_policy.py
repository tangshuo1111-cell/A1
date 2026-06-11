"""Fast-path capability policy helpers."""

from __future__ import annotations

FAST_CAPABILITY_WHITELIST: dict[str, tuple[str, ...]] = {
    "video": (
        "capability.video.subtitle_probe",
        "capability.video.short_sync_asr",
        "capability.video.duration_probe",
    ),
    "document": (
        "capability.document.probe",
        "capability.document.parse_quick",
        "capability.document.parse_pdf_quick",
        "capability.document.parse_text_or_table",
        "capability.document.summarize",
    ),
    "web": (
        "capability.web.static_fetch",
        "capability.web.probe",
    ),
    "kb": (
        "capability.kb.probe",
        "capability.kb.retrieve",
        "capability.kb.rerank",
        "capability.kb.grounding",
    ),
    "general": (
        "capability.general.direct_answer",
        "capability.general.canned_answer",
        "capability.general.weather_quick",
        "capability.general.fast_llm",
    ),
}

CROSS_LANE_GENERAL_CAPABILITIES = frozenset({
    "capability.general.fast_llm",
    "capability.general.direct_answer",
})


def cross_lane_violation_for_capabilities(lane: str, capabilities_called: list[str]) -> bool:
    """True when fast path calls a capability outside the lane whitelist."""
    allowed = set(FAST_CAPABILITY_WHITELIST.get(lane, ()))
    for cap in capabilities_called:
        if cap in allowed or cap in CROSS_LANE_GENERAL_CAPABILITIES:
            continue
        return True
    return False
