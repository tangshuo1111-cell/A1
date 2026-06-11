"""Document lane fast path implementation (Round 1)."""

from __future__ import annotations

from typing import Any

from application.chat.exit_signals import set_pending_kind_signal
from application.chat.pending_kind import PendingKind


def run_document_fast_path(
    *,
    message: str,
    context_block: str | None,
    v13_text_content: str | None,
    v13_file_content: str | bytes | None,
    v13_title: str | None = None,
    clock,
) -> tuple[str, dict[str, Any]] | None:
    from application.chat.decision_arbitrator import arbitrate_mode
    from application.ingress.lane_decision_schema import LaneDecision
    from services.capabilities.document import parse_service, summarize_service

    budget_clock = clock
    file_path = (v13_title or "").strip() or None
    fact, advice, parse_result = parse_service.probe_document_capability(
        inline_text=v13_text_content,
        file_content=v13_file_content,
        file_path=file_path,
        clock=budget_clock,
    )
    if advice.suggested_mode == "demote_to_async":
        ingress = LaneDecision(
            lane="document",
            mode="fast",
            router_source="rule",
            router_confidence=0.9,
            router_decision_ms=0,
        )
        decided_mode, decided_reason = arbitrate_mode(
            session_pending=PendingKind.NONE,
            ingress=ingress,
            main_plan=None,
            capability_advice=advice,
            clock=budget_clock,
        )
        name = file_path or "当前文档"
        extra: dict[str, Any] = {
            "fast_path": "document_fast_background_hint",
            "lane": "document",
            "mode": "fast",
            "capabilities_called": ["capability.document.probe"],
            "fast_exit_reason": "document_ocr_required",
            "capability_advice": advice,
            "capability_fact": fact,
            "arbitrator.decided_mode": decided_mode,
            "arbitrator.decided_reason": decided_reason,
            "document_page_count": fact.page_count,
            "document_ocr_required": fact.ocr_required,
        }
        if decided_mode == "complex":
            return None
        if decided_mode == "async":
            set_pending_kind_signal(extra, PendingKind.FAST_PENDING.value)
            extra["fast_exit_reason"] = "document_fast_pending"
        answer = (
            f"文档「{name}」需要 OCR 后台处理（约 {fact.page_count or '?'} 页），"
            f"我先返回任务状态。"
        )
        return answer, extra
    if advice.suggested_mode != "sync_ok":
        return None
    if parse_result is not None and parse_result.status == "success" and (parse_result.text or "").strip():
        material = str(parse_result.text).strip()
        parse_caps = [
            "capability.document.probe",
            "capability.document.parse_pdf_quick"
            if file_path and str(file_path).lower().endswith(".pdf")
            else "capability.document.parse_text_or_table",
        ]
    else:
        material, parse_caps, _parse_result = parse_service.extract_inline_material(
            inline_text=v13_text_content,
            file_content=v13_file_content,
            file_path=file_path,
        )
    if not material:
        return None
    capabilities_called = list(parse_caps)
    if "capability.document.summarize" not in capabilities_called:
        capabilities_called.append("capability.document.summarize")
    answer_text = summarize_service.summarize_document(
        message=message,
        material=material,
        context_block=context_block,
    )
    extra_out: dict[str, Any] = {
        "fast_path": "document_fast",
        "lane": "document",
        "mode": "fast",
        "capabilities_called": capabilities_called,
        "fast_exit_reason": "document_inline_summary",
        "capability_fact": fact,
        "capability_advice": advice,
        "document_page_count": fact.page_count,
        "document_ocr_required": fact.ocr_required,
    }
    return answer_text, extra_out
