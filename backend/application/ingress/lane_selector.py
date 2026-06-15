from __future__ import annotations

from .request_classifier import RequestSignals


def select_lane(signals: RequestSignals) -> tuple[str, float]:
    if signals.has_mixed_evidence_intent:
        return "general", 0.96
    if signals.source_kinds_count >= 3 and signals.has_complex_intent:
        return "general", 0.95
    if signals.has_video_url or signals.has_unsupported_video_url or signals.has_video_attachment:
        return "video", 0.98
    if signals.has_document_payload or signals.has_document_intent:
        return "document", 0.94
    if signals.has_kb_intent and not signals.has_web_intent:
        return "kb", 0.92
    if signals.has_web_url or signals.has_web_intent:
        return "web", 0.90
    if signals.has_kb_intent:
        return "kb", 0.68
    return "general", 0.55
