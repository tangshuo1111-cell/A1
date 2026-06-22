"""KI-V1-001: web URL read intent stays on web lane after MainAgent mis-label."""

from __future__ import annotations

from types import SimpleNamespace

from application.ingress.request_classifier import classify_request
from application.ingress.semantic_router import _lane_from_main_plan


def test_web_url_read_stays_web_when_main_mislabels_text_file() -> None:
    msg = "请读取这个网页并总结重点：https://example.com"
    signals = classify_request(message=msg, use_knowledge=False, v13_file_content=None, v13_text_content=None)
    plan = SimpleNamespace(
        video_url=None,
        v13_prepare_intent=SimpleNamespace(source_type="text_file", raw_source="example.com"),
        decision=SimpleNamespace(answer_channel="external", need_rag=False),
    )
    lane = _lane_from_main_plan(
        plan,
        use_knowledge=False,
        has_document_payload=signals.has_document_payload,
        signals=signals,
    )
    assert lane == "web"


def test_upload_payload_still_document_lane() -> None:
    msg = "请先解析这份资料。"
    signals = classify_request(
        message=msg,
        use_knowledge=False,
        v13_file_content=b"# doc",
        v13_text_content=None,
    )
    plan = SimpleNamespace(
        video_url=None,
        v13_prepare_intent=SimpleNamespace(source_type="text_file", raw_source="brief.md"),
        decision=SimpleNamespace(answer_channel="direct", need_rag=False),
    )
    lane = _lane_from_main_plan(
        plan,
        use_knowledge=False,
        has_document_payload=signals.has_document_payload,
        signals=signals,
    )
    assert lane == "document"
