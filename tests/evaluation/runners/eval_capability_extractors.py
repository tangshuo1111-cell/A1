from __future__ import annotations

from typing import Any


def _extra(response: dict[str, Any]) -> dict[str, Any]:
    return response.get("extra") or {}


def extract_common_exit_fields(response: dict[str, Any]) -> dict[str, Any]:
    extra = _extra(response)
    return {
        "ok": response.get("ok"),
        "answer": response.get("answer"),
        "task_id": response.get("task_id"),
        "task_status": response.get("task_status"),
        "primary_path": response.get("primary_path") or extra.get("primary_path"),
        "pending_kind": extra.get("pending_kind"),
        "lane": extra.get("lane"),
        "mode": extra.get("mode"),
        "material_sufficiency": extra.get("material_sufficiency"),
        "insufficient_evidence": extra.get("insufficient_evidence"),
        "quality_gate": {
            "pass": extra.get("quality_gate.pass"),
            "reason_codes": extra.get("quality_gate.reason_codes"),
            "need_more_material": extra.get("quality_gate.need_more_material"),
        },
        "failure_reason_code": extra.get("failure_reason_code"),
        "extra": extra,
    }


def extract_web_capability_fields(response: dict[str, Any]) -> dict[str, Any]:
    extra = _extra(response)
    return {
        "web_primary_source": extra.get("web_primary_source"),
        "web_supplement_source": extra.get("web_supplement_source"),
        "web_search_used": extra.get("web_search_used"),
        "web_evidence_chars": extra.get("web_evidence_chars"),
        "web_has_content": extra.get("web_has_content"),
        "capability_advice": extra.get("capability_advice"),
        "failure_reason_code": extra.get("failure_reason_code"),
    }


def extract_document_capability_fields(response: dict[str, Any]) -> dict[str, Any]:
    extra = _extra(response)
    source_diag = extra.get("source_diagnostics") or {}
    capability_fact = extra.get("capability_fact") or {}
    return {
        "document_ocr_required": extra.get("capability_ocr_required") or capability_fact.get("ocr_required"),
        "parser_name": extra.get("parser_name"),
        "parse_status": extra.get("v13_material_status") or source_diag.get("error_code"),
        "capability_advice": extra.get("capability_advice"),
        "pending_kind": extra.get("pending_kind"),
        "failure_reason_code": extra.get("failure_reason_code"),
        "ocr_provider": extra.get("ocr_provider"),
        "fallback_used": extra.get("fallback_used"),
    }


def extract_video_capability_fields(response: dict[str, Any]) -> dict[str, Any]:
    extra = _extra(response)
    capability_fact = extra.get("capability_fact") or {}
    metadata = capability_fact.get("metadata") or {}
    return {
        "transcript_source": extra.get("transcript_source") or metadata.get("text_source"),
        "text_source": metadata.get("text_source"),
        "provider_chain": extra.get("provider_chain")
        or extra.get("v16_web_video_asr_provider_chain")
        or extra.get("v16_local_video_asr_provider_chain"),
        "provider_attempts": extra.get("provider_attempts"),
        "provider_failures": extra.get("provider_failures"),
        "sync_strategy": extra.get("sync_strategy"),
        "background_task_id": extra.get("background_task_id") or metadata.get("background_task_id"),
        "failure_reason_code": extra.get("failure_reason_code"),
    }


def extract_kb_capability_fields(response: dict[str, Any]) -> dict[str, Any]:
    extra = _extra(response)
    return {
        "strategy_used": extra.get("strategy_used"),
        "retrieval_strategy": extra.get("v15_retrieval_strategy"),
        "kb_hits": extra.get("kb_hits"),
        "kb_top_score": extra.get("kb_top_score"),
        "kb_evidence_tier": extra.get("kb_evidence_tier"),
        "kb_sufficiency": extra.get("kb_sufficiency_level"),
        "material_sufficiency": extra.get("material_sufficiency"),
        "insufficient_evidence": extra.get("insufficient_evidence"),
        "quality_gate.reason_codes": extra.get("quality_gate.reason_codes"),
    }
