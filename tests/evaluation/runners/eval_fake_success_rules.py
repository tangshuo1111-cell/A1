from __future__ import annotations

from typing import Any


def check_common_fake_success(case: dict[str, Any], actual: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    if actual.get("task_status") == "insufficient":
        warnings.append(f"{case['case_id']}: task_status must stay canonical")
    return warnings


def check_web_fake_success(case: dict[str, Any], actual: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    if actual.get("task_status") == "succeeded":
        has_signal = any(
            (
                actual.get("web_primary_source"),
                actual.get("web_supplement_source"),
                actual.get("web_search_used"),
                actual.get("web_evidence_chars"),
            )
        )
        if not has_signal:
            warnings.append(f"{case['case_id']}: web success without web evidence signal")
    return warnings


def check_document_fake_success(case: dict[str, Any], actual: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    answer = str(actual.get("answer") or "")
    if "扫描" in case["user_input"] and actual.get("task_status") == "succeeded":
        if not any((actual.get("document_ocr_required"), actual.get("parse_status"), actual.get("pending_kind"))):
            warnings.append(f"{case['case_id']}: document success without parse/ocr signal")
    if "已完整解析" in answer and not actual.get("parse_status"):
        warnings.append(f"{case['case_id']}: claimed parser success without parse_status")
    return warnings


def check_video_fake_success(case: dict[str, Any], actual: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    if actual.get("task_status") == "succeeded":
        if not any((actual.get("transcript_source"), actual.get("text_source"), actual.get("background_task_id"))):
            warnings.append(f"{case['case_id']}: video success without transcript evidence")
    return warnings


def check_kb_fake_success(case: dict[str, Any], actual: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    answer = str(actual.get("answer") or "")
    if "知识库" in case["user_input"] and actual.get("task_status") in ("succeeded", "partial"):
        if not any((actual.get("strategy_used"), actual.get("kb_hits"), actual.get("kb_evidence_tier"))):
            warnings.append(f"{case['case_id']}: kb answer without retrieval evidence")
    if "知识库显示" in answer and not any((actual.get("kb_hits"), actual.get("strategy_used"))):
        warnings.append(f"{case['case_id']}: answer claims KB evidence without retrieval signals")
    return warnings
