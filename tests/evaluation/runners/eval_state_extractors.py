from __future__ import annotations

from typing import Any


def _extra(response: dict[str, Any]) -> dict[str, Any]:
    return response.get("extra") or {}


def extract_common_state_fields(response: dict[str, Any]) -> dict[str, Any]:
    extra = _extra(response)
    return {
        "task_status": response.get("task_status"),
        "pending_kind": extra.get("pending_kind"),
        "primary_path": response.get("primary_path") or extra.get("primary_path"),
        "mode": extra.get("mode"),
        "lane": extra.get("lane"),
        "router_lane": extra.get("router_lane"),
        "executor_profile": extra.get("executor_profile"),
        "task_id": response.get("task_id") or extra.get("task_id"),
        "material_sufficiency": extra.get("material_sufficiency"),
        "insufficient_evidence": extra.get("insufficient_evidence"),
        "quality_gate": {
            "pass": extra.get("quality_gate.pass"),
            "reason_codes": extra.get("quality_gate.reason_codes"),
            "need_more_material": extra.get("quality_gate.need_more_material"),
        },
        "failure_reason_code": extra.get("failure_reason_code"),
        "answer": response.get("answer"),
        "extra": extra,
    }


def extract_session_state_fields(response: dict[str, Any]) -> dict[str, Any]:
    extra = _extra(response)
    return {
        "session_id": response.get("session_id"),
        "context_block": extra.get("context_block"),
        "history_used": extra.get("history_used") or extra.get("v8_middle_history_used"),
        "session_stage": extra.get("session_stage"),
        "prev_video_ref": extra.get("prev_video_ref"),
        "pending_video": extra.get("pending_video"),
        "stitch_slot": extra.get("stitch_slot"),
        "previous_turn_used": extra.get("previous_turn_used"),
        "followup_detected": extra.get("followup_detected"),
    }


def extract_pending_state_fields(response: dict[str, Any]) -> dict[str, Any]:
    extra = _extra(response)
    return {
        "pending_kind": extra.get("pending_kind"),
        "pending_reference": extra.get("v15_pending_reference") or extra.get("pending_reference"),
        "material_pending": extra.get("pending_kind") == "material_pending",
        "partial_pending": extra.get("pending_kind") == "partial_pending",
    }


def extract_commit_state_fields(response: dict[str, Any]) -> dict[str, Any]:
    extra = _extra(response)
    answer = str(response.get("answer") or "")
    return {
        "commit_status": extra.get("commit_status"),
        "commit_result": extra.get("commit_result"),
        "saved_source_id": extra.get("saved_source_id") or extra.get("pending_source_id"),
        "retrieval_after_commit": extra.get("retrieval_after_commit"),
        "answer_commit_signal": ("保存成功" in answer) or ("已保存" in answer),
    }


def extract_task_state_fields(response: dict[str, Any]) -> dict[str, Any]:
    extra = _extra(response)
    capability_fact = extra.get("capability_fact") or {}
    metadata = capability_fact.get("metadata") or {}
    return {
        "task_id": response.get("task_id") or extra.get("task_id"),
        "task_status": response.get("task_status"),
        "background_task_id": extra.get("background_task_id") or metadata.get("background_task_id"),
        "task_result_status": extra.get("task_result_status"),
        "task_error_code": extra.get("task_error_code"),
    }


def extract_followup_state_fields(previous_steps: list[dict[str, Any]], current_response: dict[str, Any]) -> dict[str, Any]:
    extra = _extra(current_response)
    answer = str(current_response.get("answer") or "")
    previous = previous_steps[-1] if previous_steps else {}
    previous_answer = str((previous.get("actual") or {}).get("answer") or "")
    return {
        "has_previous_steps": bool(previous_steps),
        "followup_detected": extra.get("followup_detected") or ("继续刚才" in answer),
        "previous_turn_used": extra.get("previous_turn_used"),
        "answer_mentions_previous": ("刚才" in answer) or (previous_answer[:12] and previous_answer[:12] in answer),
    }
