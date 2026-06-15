"""Fast path delivery helpers — result/trace assembly (Cleanup C1)."""

from __future__ import annotations

import time
import uuid
from typing import Any

from application.chat.budget_clock import SLA_BUDGET_MS
from application.chat.chat_contracts import resolve_background_task_id
from application.chat.executors.fast_lanes.fast_capability_policy import (
    cross_lane_violation_for_capabilities,
)
from application.chat.exit_signals import (
    EXIT_SIGNAL_PRIMARY_PATH,
    pending_kind_signal_from_extra,
    set_material_sufficiency_signal,
    set_mode_signal,
)
from application.chat.pending_kind import PendingKind
from application.chat.turn_exit_extra import build_common_exit_extra
from application.chat.turn_exit_gate import apply_turn_exit_to_chat_turn
from application.chat.turn_facts import TurnFacts
from application.chat.turn_response_builder import build_chat_turn_result
from schemas import ChatTurnResult
from services.capabilities.contracts import CapabilityAdvice
from tools.video.errors import VIDEO_URL_UNSUPPORTED


def build_fast_trace_extra(
    *,
    lane: str,
    capabilities_called: list[str],
    elapsed_ms: int,
    exit_reason: str,
    cross_lane_violation: bool = False,
) -> dict[str, Any]:
    return {
        "fast_lane_name": lane,
        "capabilities_called": capabilities_called,
        "cross_lane_violation": cross_lane_violation,
        "fast_exit_reason": exit_reason,
        "fast_first_response_ms": elapsed_ms,
    }


def should_demote_fast_to_async(extra: dict[str, Any]) -> bool:
    advice = extra.get("capability_advice")
    if isinstance(advice, CapabilityAdvice) and advice.suggested_mode == "demote_to_async":
        return True
    suggested = str(extra.get("capability_suggested_mode") or "").strip()
    if suggested == "demote_to_async":
        return True
    return str(extra.get("arbitrator.decided_mode") or "") == "async"


def build_fast_result(
    *,
    answer: str,
    session_id: str | None,
    request_id: str | None,
    elapsed_ms: int,
    extra: dict[str, Any],
) -> ChatTurnResult:
    capabilities_called = list(extra.get("capabilities_called") or [])
    lane_for_audit = str(extra.get("lane") or extra.get("fast_lane_name") or extra.get("router_lane") or "")
    if lane_for_audit and capabilities_called:
        extra["cross_lane_violation"] = cross_lane_violation_for_capabilities(
            lane_for_audit, capabilities_called
        )
    fast_path = str(extra.get("fast_path") or "fast")
    lane = str(extra.get("lane") or "")
    if not lane:
        if fast_path.startswith("local_") or fast_path in {"weather", "weather_failed"}:
            lane = fast_path
        else:
            lane = str(extra.get("router_lane") or fast_path)
    capabilities_called = list(extra.get("capabilities_called") or [])
    fast_task_id = str(
        extra.get("fast_task_id")
        or f"fast-{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}"
    )
    collab_trace = [f"v15:needs_retrieval_plan=False path={fast_path}", f"v15:fast_path={fast_path}"]
    background_task_id = resolve_background_task_id(extra=extra)
    pending_kind = pending_kind_signal_from_extra(extra) or ""
    is_fast_pending = bool(background_task_id) or pending_kind == PendingKind.FAST_PENDING.value
    top_task_id: str | None = None
    answer_type = "fast_path"
    if is_fast_pending and background_task_id:
        top_task_id = background_task_id
        answer_type = "fast_pending"
        pending_kind = pending_kind or PendingKind.FAST_PENDING.value
    merged_extra: dict[str, Any] = build_common_exit_extra(
        extra_base={
            "lane": lane,
            EXIT_SIGNAL_PRIMARY_PATH: fast_path,
            "fast_path": True,
            "agno": True,
            "collaboration_trace": collab_trace,
            "v4_min_collab": True,
            "v4_path_fingerprint": fast_path,
            "v4_nodes": {},
            "v6_takeover": True,
            "v6_main_task_id": fast_task_id,
            "v6_middle_web_reason": "fast_path_skip",
            "v6_middle_material_insufficient": False,
            "v6_plan_web_mode": "fast_skip",
            "v6_plan_answer_composition": "default",
            "v6_plan_force_skip_evidence": True,
            "v6_middle_kb_tier": "none",
            "v6_middle_insufficiency_signal": "none",
            "v15_plan_id": fast_task_id,
            "v15_bundle_id": f"{fast_task_id}-bundle",
            "v15_needs_retrieval": False,
            "v15_retrieval_strategy": "fast_skip",
            "v15_needs_pending": False,
            "v15_pending_reference": "none",
            "v15_answer_mode": "direct",
            "v15_tools_allowed": [],
            "v15_material_sufficiency": "sufficient",
            "v15_execution_status": "ok",
            "v15_retrieved_chunks_count": 0,
            "fast_lane_name": lane,
            "capabilities_called": capabilities_called,
            "cross_lane_violation": bool(extra.get("cross_lane_violation", False)),
            "fast_exit_reason": str(extra.get("fast_exit_reason") or "fast_path_complete"),
            "fast_first_response_ms": elapsed_ms,
            "agent_timings": {
                "session_snapshot_ms": int(extra.get("session_snapshot_ms", 0) or 0),
                "main_ms": 0,
                "middle_ms": 0,
                "answer_ms": int(extra.get("fast_answer_ms", 0) or 0),
                "session_update_ms": 0,
                "extra_build_ms": 0,
                "total_ms": elapsed_ms,
            },
            **extra,
            "sla_deadline_ms": SLA_BUDGET_MS,
        },
        ingress=None,
        mode="fast",
        executor_profile="fast",
        progress_stage="completed",
        elapsed_ms=elapsed_ms,
    )
    set_mode_signal(merged_extra, "fast")
    set_material_sufficiency_signal(merged_extra, "sufficient")
    if top_task_id:
        merged_extra["partial_answer_text"] = answer
        merged_extra.setdefault(
            "next_action",
            "后台任务处理中，请轮询 /tasks/{task_id}/result 获取完整结果。",
        )
        merged_extra["progress_stage"] = str(extra.get("progress_stage") or "queued")
    primary_path = str(
        merged_extra.get(EXIT_SIGNAL_PRIMARY_PATH)
        or extra.get("fast_path")
        or "fast"
    )
    try:
        pk = PendingKind(pending_kind) if pending_kind else PendingKind.NONE
    except ValueError:
        pk = PendingKind.NONE
    video_hard_failure = str(extra.get("v16_video_error_code") or "").strip() == VIDEO_URL_UNSUPPORTED
    facts = TurnFacts(
        router_lane=lane,
        effective_mode="fast",
        public_mode="fast",
        executor_profile="fast",
        pending_kind=pk,
        primary_path_candidate=primary_path,
        async_pending=answer_type == "fast_pending",
        answer_type=answer_type,
        hard_failure=video_hard_failure,
        legacy_task_status="failed" if video_hard_failure else None,
        pipeline_ok=not video_hard_failure,
    )
    return apply_turn_exit_to_chat_turn(
        build_chat_turn_result(
            answer=answer,
            session_id=session_id,
            request_id=request_id,
            task_id=top_task_id,
            answer_type=answer_type,
            extra=merged_extra,
            elapsed_ms=elapsed_ms,
            pipeline_ok=not video_hard_failure,
            ok=not video_hard_failure,
        ),
        facts=facts,
        effective_mode="fast",
    )
