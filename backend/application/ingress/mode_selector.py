from __future__ import annotations

from application.chat.complexity_policy import STRONG_COMPLEX_REASON_CODES
from config.feature_flags import complexity_policy_active

from .request_classifier import RequestSignals


def select_mode(
    *,
    lane: str,
    signals: RequestSignals,
    message: str,
    complex_candidate: bool = False,
    complex_reason_codes: tuple[str, ...] = (),
) -> tuple[str, float]:
    msg = (message or "").strip()
    if lane == "video" and signals.has_long_video_hint:
        return "async", 0.98
    if lane == "web" and signals.asks_background_processing:
        return "async", 0.95
    if lane == "general" and signals.asks_background_processing and signals.has_mixed_evidence_intent and len(signals.urls) > 1:
        return "async", 0.9
    if signals.has_mixed_evidence_intent:
        return "complex", 0.96
    if signals.has_ocr_intent:
        return "complex", 0.94
    if complexity_policy_active():
        if complex_candidate and any(code in STRONG_COMPLEX_REASON_CODES for code in complex_reason_codes):
            return "complex", 0.92
        if complex_candidate:
            return "fast", 0.91
        return "fast", 0.93
    if signals.has_complex_intent or len(msg) > 180:
        return "complex", 0.86
    if lane == "general" and len(msg) > 80:
        return "complex", 0.72
    return "fast", 0.93
