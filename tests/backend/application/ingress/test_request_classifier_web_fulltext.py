from __future__ import annotations

from application.ingress.lane_selector import select_lane
from application.ingress.request_classifier import classify_request


def test_web_fulltext_request_does_not_trigger_document_intent_from_extract_word() -> None:
    sig = classify_request(
        message="https://example.com/article 把整个网页的全文提取出来给我",
        use_knowledge=False,
        v13_file_content=None,
        v13_text_content=None,
        attachments=None,
    )
    assert sig.has_web_url is True
    assert sig.has_web_intent is True
    assert sig.has_document_intent is False
    assert select_lane(sig)[0] == "web"


def test_docs_subdomain_url_does_not_trigger_document_intent() -> None:
    sig = classify_request(
        message="https://docs.apifox.com/introduction 把整个网页的全文提取出来给我",
        use_knowledge=False,
        v13_file_content=None,
        v13_text_content=None,
        attachments=None,
    )
    assert sig.has_web_url is True
    assert sig.has_web_intent is True
    assert sig.has_document_intent is False
    assert select_lane(sig)[0] == "web"


def test_explicit_doc_extension_still_triggers_document_intent() -> None:
    sig = classify_request(
        message="请总结 report.docx 的核心内容",
        use_knowledge=False,
        v13_file_content=None,
        v13_text_content=None,
        attachments=None,
    )
    assert sig.has_document_intent is True
    assert select_lane(sig)[0] == "document"
