from __future__ import annotations

from typing import Any


def _answer_text(actual: dict[str, Any]) -> str:
    return str((actual.get("grounding") or {}).get("answer") or actual.get("answer") or "")


def _has_any_value(mapping: dict[str, Any], keys: list[str]) -> bool:
    for key in keys:
        value = mapping.get(key)
        if value not in (None, "", [], {}, ()):
            return True
    return False


def check_common_agent_collaboration(case: dict[str, Any], actual: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    task_status = str((actual.get("common") or {}).get("task_status") or "")
    if task_status == "insufficient":
        issues.append(f"{case['case_id']}: task_status=insufficient is illegal")
    return issues


def check_main_plan_observable(case: dict[str, Any], actual: dict[str, Any]) -> list[str]:
    plan = actual.get("plan") or {}
    if _has_any_value(
        plan,
        [
            "main_plan",
            "route_decision",
            "routing_explain",
            "router_source",
            "complex_candidate",
            "material_need",
            "v6_main_pan_renwu",
        ],
    ):
        return []
    return [f"{case['case_id']}: missing main plan observable signals"]


def check_middle_material_observable(case: dict[str, Any], actual: dict[str, Any]) -> list[str]:
    material = actual.get("material") or {}
    if _has_any_value(
        material,
        [
            "material_sufficiency",
            "retrieved_chunks",
            "web_material",
            "document_material",
            "video_material",
            "kb_hits",
            "v6_middle_pan_laiyuan",
        ],
    ):
        return []
    return [f"{case['case_id']}: missing middle material observable signals"]


def check_answer_grounded_in_material(case: dict[str, Any], actual: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    answer = _answer_text(actual)
    grounding = actual.get("grounding") or {}
    material = actual.get("material") or {}

    claims_kb = "根据知识库" in answer or "知识库明确" in answer
    claims_web = "完整阅读网页" in answer or "根据网页内容" in answer
    claims_video = "视频里主要讲了" in answer or "看完视频" in answer
    claims_document = "根据上传文档" in answer or "文档明确写到" in answer

    if claims_kb and not _has_any_value(material, ["kb_hits", "kb_evidence_tier", "retrieved_chunks", "v6_middle_pan_laiyuan"]):
        issues.append(f"{case['case_id']}: claimed KB grounding without KB material signal")
    if claims_web and not _has_any_value(material, ["web_material", "web_has_content", "web_evidence_chars", "web_primary_source"]):
        issues.append(f"{case['case_id']}: claimed web grounding without web material signal")
    if claims_video and not _has_any_value(material, ["video_material", "v7_middle_pan_video_source", "v11_middle_video_url_text_source"]):
        issues.append(f"{case['case_id']}: claimed video grounding without transcript/video material signal")
    if claims_document and not _has_any_value(material, ["document_material", "temporary_materials"]):
        issues.append(f"{case['case_id']}: claimed document grounding without document material signal")

    if grounding.get("groundedness_markers", {}).get("claims_strong_conclusion") and not _has_any_value(
        material,
        ["retrieved_chunks", "web_material", "document_material", "video_material", "kb_hits"],
    ):
        issues.append(f"{case['case_id']}: strong conclusion without observable material support")
    return issues


def check_quality_gate_honesty(case: dict[str, Any], actual: dict[str, Any]) -> list[str]:
    quality = actual.get("quality") or {}
    if not _has_any_value(quality, ["quality_gate", "reason_codes", "need_second_round", "need_more_material", "quality_gate_passed"]):
        return [f"{case['case_id']}: missing quality gate observable signals"]
    return []


def check_evidence_insufficiency_honesty(case: dict[str, Any], actual: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    common = actual.get("common") or {}
    quality = actual.get("quality") or {}
    grounding = actual.get("grounding") or {}
    answer = _answer_text(actual)

    insufficient = bool(common.get("insufficient_evidence"))
    material_sufficiency = str(common.get("material_sufficiency") or "")
    reason_codes = [str(code) for code in (quality.get("reason_codes") or [])]
    weak_material = material_sufficiency in {"insufficient", "no_match", "low_confidence", "partial"} or insufficient or ("kb_insufficient" in reason_codes)

    if not weak_material:
        return issues

    has_limitation = grounding.get("groundedness_markers", {}).get("has_limitation_statement")
    strong_claim = grounding.get("groundedness_markers", {}).get("claims_strong_conclusion")
    if strong_claim and not has_limitation:
        issues.append(f"{case['case_id']}: evidence insufficiency not honestly reflected in answer")
    if ("已经达到准生产级" in answer or "完整如下" in answer) and not has_limitation:
        issues.append(f"{case['case_id']}: absolute conclusion given under insufficient evidence")
    return issues


def check_multi_source_alignment(case: dict[str, Any], actual: dict[str, Any]) -> list[str]:
    if "multi_source" not in str(case.get("category") or ""):
        return []
    issues: list[str] = []
    answer = _answer_text(actual)
    material = actual.get("material") or {}
    mentions_kb = "知识库" in answer
    mentions_web = "网页" in answer or "官方教程" in answer or "Python 教程" in answer or "python 官方教程" in answer.lower()
    has_kb = _has_any_value(material, ["kb_hits", "kb_evidence_tier", "retrieved_chunks"])
    has_web = _has_any_value(material, ["web_material", "web_has_content", "web_evidence_chars"])
    if mentions_kb and mentions_web:
        if not has_kb:
            issues.append(f"{case['case_id']}: claimed multi-source answer without KB signal")
        if not has_web:
            issues.append(f"{case['case_id']}: claimed multi-source answer without web signal")
    return issues


def check_video_material_honesty(case: dict[str, Any], actual: dict[str, Any]) -> list[str]:
    if "video" not in str(case.get("category") or ""):
        return []
    material = actual.get("material") or {}
    answer = _answer_text(actual)
    has_video_signal = _has_any_value(material, ["video_material", "v7_middle_pan_video_source", "v11_middle_video_url_text_source"])
    if not has_video_signal and ("视频里主要讲了" in answer or "看完视频" in answer or "视频内容主要是" in answer):
        return [f"{case['case_id']}: video details claimed without transcript/material signal"]
    return []


def check_second_round_observability(case: dict[str, Any], actual: dict[str, Any]) -> list[str]:
    expected = case.get("expected") or {}
    behavior = str(expected.get("expected_quality_gate_behavior") or "") + " " + str(expected.get("expected_grounding_behavior") or "")
    if "second_round" not in behavior and "material_gap" not in behavior:
        return []
    second_round = actual.get("second_round") or {}
    if _has_any_value(second_round, ["need_second_round", "second_round_used", "feedback_used", "supplement_used", "supplementary_retrieve", "feedback_gate_result", "used_rounds", "material_gap"]):
        return []
    return [f"{case['case_id']}: second-round or material-gap observability missing"]
