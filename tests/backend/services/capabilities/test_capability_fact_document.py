"""S7 — document capability contract when ENABLE_CAPABILITY_FACT_DOCUMENT is on."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from application.chat.budget_clock import BudgetClock
from config import feature_flags
from services.capabilities.document import parse_service
from tools.document.errors import SCANNED_PDF_REQUIRES_OCR
from tools.document.tool_result import DocumentToolResult


@pytest.fixture
def enable_capability_fact_document(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_CAPABILITY_FACT_DOCUMENT", True)
    monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_DECISION_ARBITRATOR", True)
    monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_BUDGET_CLOCK_V2", True)


def test_probe_document_capability_ocr_required_with_page_count() -> None:
    parse_result = DocumentToolResult(
        tool_name="parse_pdf",
        status="failed",
        source_type="pdf",
        error_code=SCANNED_PDF_REQUIRES_OCR,
        metadata={"page_count": 12, "ocr_required": True},
    )
    with patch.object(parse_service, "parse_text_or_table", return_value=parse_result):
        fact, advice, result = parse_service.probe_document_capability(
            file_path="scan.pdf",
        )
    assert result is parse_result
    assert fact.ocr_required is True
    assert fact.page_count == 12
    assert advice.suggested_mode == "demote_to_async"
    assert advice.reason == "ocr_required"


def test_probe_document_capability_sync_ok_for_inline_text() -> None:
    fact, advice, result = parse_service.probe_document_capability(
        inline_text="这是可直接摘要的文档正文。",
    )
    assert result is None
    assert fact.ocr_required is False
    assert fact.page_count == 1
    assert advice.suggested_mode == "sync_ok"


def test_probe_document_capability_parse_success() -> None:
    parse_result = DocumentToolResult(
        tool_name="parse_pdf",
        status="success",
        source_type="pdf",
        text="PDF 可提取正文内容。",
        metadata={"page_count": 3},
        quality={"quality_level": "good"},
    )
    with patch.object(parse_service, "parse_text_or_table", return_value=parse_result):
        fact, advice, _result = parse_service.probe_document_capability(file_path="doc.pdf")
    assert fact.page_count == 3
    assert fact.ocr_required is False
    assert advice.suggested_mode == "sync_ok"
    assert fact.metadata["parser_name"] == "parse_pdf"


def test_parse_text_or_table_does_not_forward_session_id_to_parser() -> None:
    captured: dict[str, object] = {}

    def _fake_call_parse_tool(tool_name: str, **kwargs):
        captured["tool_name"] = tool_name
        captured["kwargs"] = kwargs
        return DocumentToolResult(
            tool_name=tool_name,
            status="success",
            source_type="docx",
            text="ok",
        )

    with patch.object(parse_service, "call_parse_tool", side_effect=_fake_call_parse_tool):
        result = parse_service.parse_text_or_table(
            "demo.docx",
            file_content=b"docx-bytes",
            session_id="session-should-not-pass",
        )
    assert result.status == "success"
    assert captured["tool_name"] == "parse_docx"
    assert captured["kwargs"] == {
        "file_path": "demo.docx",
        "file_content": b"docx-bytes",
    }


def test_run_document_fast_path_demotes_on_ocr_required(
    enable_capability_fact_document,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from application.chat.executors.fast_lanes import document_fast_impl
    from services.capabilities.contracts import CapabilityAdvice, CapabilityFact

    fact = CapabilityFact(
        lane="document",
        probe_elapsed_ms=40,
        page_count=8,
        ocr_required=True,
        quality_level="empty",
    )
    advice = CapabilityAdvice(suggested_mode="demote_to_async", reason="ocr_required")
    monkeypatch.setattr(
        parse_service,
        "probe_document_capability",
        lambda **_k: (fact, advice, None),
    )
    monkeypatch.setattr(
        parse_service,
        "extract_inline_material",
        lambda **_k: (_ for _ in ()).throw(AssertionError("extract must not run")),
    )

    out = document_fast_impl.run_document_fast_path(
        message="总结这份 PDF",
        context_block=None,
        v13_text_content=None,
        v13_file_content=b"%PDF",
        v13_title="scan.pdf",
        clock=BudgetClock.start(),
    )
    assert out is not None
    answer, extra = out
    assert "OCR" in answer
    assert extra["document_page_count"] == 8
    assert extra["document_ocr_required"] is True
    assert extra["arbitrator.decided_mode"] == "async"


def test_enqueue_document_passes_prefilled_fact(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.capabilities.contracts import CapabilityFact

    monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_ASYNC_CONTROL_PLANE_V2", True)
    created: list[dict] = []
    monkeypatch.setattr(
        "services.capabilities.document.ocr_service.task_job_store.create_task",
        lambda task_id, **kwargs: created.append({"task_id": task_id, **kwargs}) or None,
    )
    monkeypatch.setattr(
        "services.capabilities.document.ocr_service.enqueue_async_task",
        lambda _msg: "memory",
    )
    monkeypatch.setattr(
        "services.capabilities.document.ocr_service.ensure_async_workers_started",
        lambda: None,
    )
    monkeypatch.setattr(
        "services.capabilities.document.ocr_service.task_job_store.update_task_async_metadata",
        lambda *a, **k: None,
    )
    fact = CapabilityFact(
        lane="document",
        probe_elapsed_ms=55,
        page_count=10,
        ocr_required=True,
        quality_level="empty",
    )
    from services.capabilities.document import ocr_service

    ocr_service.enqueue_document_ocr_task(
        file_path="D:\\docs\\scan.pdf",
        session_id="s7",
        prefilled_fact=fact,
    )
    assert created
    meta = created[0]["metadata"]
    assert meta["capability_page_count"] == 10
    assert meta["capability_ocr_required"] is True
