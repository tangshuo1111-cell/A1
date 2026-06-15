from __future__ import annotations

from typing import Any


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _extra(response: dict[str, Any]) -> dict[str, Any]:
    return _as_dict(response.get("extra"))


def _quality_gate(response: dict[str, Any]) -> dict[str, Any]:
    extra = _extra(response)
    return _as_dict(extra.get("quality_gate"))


def _first_present(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", [], {}, ()):
            return value
    return None


def extract_agent_common_fields(response: dict[str, Any]) -> dict[str, Any]:
    extra = _extra(response)
    return {
        "task_status": response.get("task_status"),
        "primary_path": response.get("primary_path") or extra.get("primary_path"),
        "mode": extra.get("mode"),
        "lane": extra.get("lane") or extra.get("router_lane"),
        "router_lane": extra.get("router_lane"),
        "pending_kind": extra.get("pending_kind"),
        "material_sufficiency": extra.get("material_sufficiency"),
        "insufficient_evidence": extra.get("insufficient_evidence"),
        "failure_reason_code": extra.get("failure_reason_code"),
        "executor_profile": extra.get("executor_profile"),
        "answer": response.get("answer"),
        "answer_char_count": extra.get("answer_char_count"),
        "extra": extra,
    }


def extract_main_plan_fields(response: dict[str, Any]) -> dict[str, Any]:
    extra = _extra(response)
    return {
        "main_plan": _first_present(extra.get("main_plan"), extra.get("plan")),
        "route_decision": _first_present(extra.get("route_decision"), response.get("primary_path"), extra.get("primary_path")),
        "routing_explain": extra.get("routing_explain"),
        "router_source": extra.get("router_source"),
        "complex_candidate": extra.get("complex_candidate") if "complex_candidate" in extra else extra.get("is_complex_task"),
        "needs_retrieval": extra.get("needs_retrieval"),
        "retrieval_strategy": extra.get("retrieval_strategy"),
        "needs_pending": extra.get("needs_pending"),
        "answer_mode": extra.get("answer_mode"),
        "material_need": extra.get("material_need"),
        "tools_allowed": extra.get("tools_allowed"),
        "plan_confidence": extra.get("plan_confidence"),
        "v6_main_pan_renwu": extra.get("v6_main_pan_renwu"),
        "v6_main_pan_allow_kb": extra.get("v6_main_pan_allow_kb"),
        "v6_main_pan_allow_web": extra.get("v6_main_pan_allow_web"),
        "v6_main_pan_celue": extra.get("v6_main_pan_celue"),
    }


def extract_middle_material_fields(response: dict[str, Any]) -> dict[str, Any]:
    extra = _extra(response)
    capability_fact = _as_dict(extra.get("capability_fact"))
    retrieval_snapshot = _as_dict(extra.get("retrieval_snapshot"))
    material_bundle = _as_dict(extra.get("material_bundle"))
    return {
        "material_bundle": material_bundle,
        "retrieved_chunks": _first_present(extra.get("retrieved_chunks"), retrieval_snapshot.get("retrieved_chunks"), material_bundle.get("retrieved_chunks")),
        "retrieval_snapshot": retrieval_snapshot,
        "knowledge_block": _first_present(extra.get("knowledge_block"), material_bundle.get("knowledge_block")),
        "web_material": _first_present(extra.get("web_block"), extra.get("web_material"), material_bundle.get("web_material")),
        "document_material": _first_present(extra.get("document_material"), material_bundle.get("document_material"), extra.get("temporary_materials")),
        "video_material": _first_present(extra.get("video_material"), material_bundle.get("video_material"), extra.get("v7_middle_pan_video_source"), extra.get("v11_middle_video_url_text_source")),
        "source_count": _first_present(extra.get("source_count"), material_bundle.get("source_count")),
        "source_ids": _first_present(extra.get("source_ids"), material_bundle.get("source_ids")),
        "chunk_ids": _first_present(extra.get("chunk_ids"), material_bundle.get("chunk_ids")),
        "material_sufficiency": extra.get("material_sufficiency"),
        "kb_hits": _first_present(extra.get("kb_hits"), extra.get("kb_hit_count"), retrieval_snapshot.get("kb_hits")),
        "kb_top_score": _first_present(extra.get("kb_top_score"), retrieval_snapshot.get("kb_top_score")),
        "kb_evidence_tier": _first_present(extra.get("kb_evidence_tier"), retrieval_snapshot.get("kb_evidence_tier")),
        "web_has_content": extra.get("web_has_content"),
        "web_evidence_chars": extra.get("web_evidence_chars"),
        "web_primary_source": extra.get("web_primary_source"),
        "failures": _first_present(extra.get("failures"), material_bundle.get("failures")),
        "temporary_materials": _first_present(extra.get("temporary_materials"), material_bundle.get("temporary_materials")),
        "source_briefs": _first_present(extra.get("source_briefs"), material_bundle.get("source_briefs")),
        "comparison_matrix": _first_present(extra.get("comparison_matrix"), material_bundle.get("comparison_matrix")),
        "feedback_gate_result": _first_present(extra.get("feedback_gate_result"), material_bundle.get("feedback_gate_result")),
        "used_rounds": _first_present(extra.get("used_rounds"), material_bundle.get("used_rounds")),
        "v6_middle_pan_gou": extra.get("v6_middle_pan_gou"),
        "v6_middle_pan_bukong": extra.get("v6_middle_pan_bukong"),
        "v6_middle_pan_laiyuan": extra.get("v6_middle_pan_laiyuan"),
        "v6_middle_pan_que": extra.get("v6_middle_pan_que"),
        "v6_middle_pan_xia": extra.get("v6_middle_pan_xia"),
        "v7_middle_pan_video_source": extra.get("v7_middle_pan_video_source"),
        "v7_middle_pan_video_error": extra.get("v7_middle_pan_video_error"),
        "v11_middle_video_url_text_source": extra.get("v11_middle_video_url_text_source"),
    }


def extract_answer_grounding_fields(response: dict[str, Any]) -> dict[str, Any]:
    extra = _extra(response)
    answer = str(response.get("answer") or "")
    lowered = answer.lower()
    return {
        "answer": answer,
        "answer_sources": _first_present(extra.get("answer_sources"), extra.get("cited_sources")),
        "cited_sources": extra.get("cited_sources"),
        "used_chunks": extra.get("used_chunks"),
        "groundedness_markers": {
            "mentions_knowledge_base": "知识库" in answer,
            "mentions_webpage": ("网页" in answer) or ("教程" in answer) or ("python" in lowered),
            "mentions_document": ("文档" in answer) or ("材料" in answer),
            "mentions_video": ("视频" in answer) or ("字幕" in answer) or ("转写" in answer),
            "has_limitation_statement": any(token in answer for token in ("无法确认", "证据不足", "当前材料不足", "基于当前", "如果", "可能", "暂时")),
            "claims_strong_conclusion": any(token in answer for token in ("可以确定", "明确说明", "完整如下", "已经达到", "毫无疑问", "视频里主要讲了")),
        },
        "insufficient_evidence": extra.get("insufficient_evidence"),
        "answer_mode": extra.get("answer_mode"),
        "limitation_statement": _first_present(extra.get("limitation_statement"), extra.get("limitations")),
        "evidence_summary": extra.get("evidence_summary"),
        "v6_answer_pan_dafengshi": extra.get("v6_answer_pan_dafengshi"),
        "v6_answer_pan_jiegou": extra.get("v6_answer_pan_jiegou"),
        "v6_answer_pan_baoshou": extra.get("v6_answer_pan_baoshou"),
    }


def extract_quality_gate_fields(response: dict[str, Any]) -> dict[str, Any]:
    extra = _extra(response)
    qg = _quality_gate(response)
    return {
        "quality_gate": qg,
        "quality_gate_pass": _first_present(qg.get("pass"), extra.get("quality_gate.pass")),
        "reason_codes": _first_present(qg.get("reason_codes"), extra.get("quality_gate.reason_codes"), []),
        "need_second_round": _first_present(qg.get("need_second_round"), extra.get("quality_gate.need_second_round")),
        "need_more_material": _first_present(qg.get("need_more_material"), extra.get("quality_gate.need_more_material")),
        "quality_gate_passed": extra.get("quality_gate_passed"),
        "material_gap": extra.get("material_gap"),
        "partial_answer": extra.get("partial_answer"),
    }


def extract_second_round_fields(response: dict[str, Any]) -> dict[str, Any]:
    extra = _extra(response)
    return {
        "need_second_round": extra.get("quality_gate.need_second_round"),
        "second_round_used": extra.get("second_round_used"),
        "feedback_used": extra.get("feedback_used"),
        "supplement_used": extra.get("supplement_used"),
        "supplementary_retrieve": extra.get("supplementary_retrieve"),
        "feedback_gate_result": extra.get("feedback_gate_result"),
        "used_rounds": extra.get("used_rounds"),
        "material_gap": extra.get("material_gap"),
        "deadline_limited": extra.get("hard_deadline_limited"),
    }
