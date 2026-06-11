from __future__ import annotations

import re
import time
from typing import Any

from application.chat.budget_clock import SLA_BUDGET_MS, format_ms
from application.chat.exit_signals import EXIT_SIGNAL_PRIMARY_PATH
from application.chat.pending_kind import PendingKind
from application.chat.turn_exit_extra import build_common_exit_extra
from application.chat.turn_exit_gate import apply_turn_exit_to_chat_turn
from application.chat.turn_facts import TurnFacts
from application.chat.turn_response_builder import build_chat_turn_result
from schemas import ChatTurnResult
from services.capabilities.contracts import CapabilityFact
from services.execution import task_plane_service

_ASYNC_LANE_ANSWERS: dict[str, str] = {
    "video": "这个请求已进入视频后台处理通道，我先不阻塞首响应。",
    "web": "这个请求已进入网页后台抓取通道，我先返回任务状态。",
    "document": "这个请求已进入文档 OCR 后台通道，我先返回任务状态。",
}
_ASYNC_NEXT_ACTIONS: dict[str, str] = {
    "video": "视频已转后台处理，请轮询 /tasks/{task_id}/result 获取结果。",
    "web": "网页重抓取已排队，请稍后查看任务结果。",
    "document": "文档 OCR 已排队，请轮询 /tasks/{task_id}/result 获取结果。",
}
_ASYNC_CAPABILITIES: dict[str, list[str]] = {
    "video": ["capability.video.background_task"],
    "web": ["capability.web.background_task"],
    "document": ["capability.document.background_task"],
}

# Stable contract surface for S7b tests and frontend polling.
ASYNC_PENDING_TOP_LEVEL_FIELDS = (
    "ok",
    "answer",
    "session_id",
    "request_id",
    "task_id",
    "answer_type",
    "task_status",
    "primary_path",
    "pipeline_ok",
    "extra",
    "workflow_elapsed_ms",
)
ASYNC_PENDING_EXTRA_FIELDS = (
    "lane",
    "primary_path",
    "mode",
    "agno",
    "fast_path",
    "capabilities_called",
    "progress_stage",
    "next_action",
    "queue_backend",
    "router_lane",
    "router_source",
    "router_confidence",
    "router_fallback",
    "router_decision_ms",
    "sla_deadline_ms",
    "elapsed_ms",
    "timing_total_ms",
    "remaining_ms_at_answer_start",
    "agent_timings",
    "pending_agents",
    "completed_agents",
    "pending_kind",
    "partial_answer_text",
)


def _first_url(message: str) -> str:
    match = re.search(r"https?://[^\s]+", message or "", flags=re.IGNORECASE)
    return match.group(0) if match else ""


def _resolve_document_path(*, message: str, file_path: str | None) -> str:
    if file_path and str(file_path).strip():
        return str(file_path).strip()
    msg = (message or "").strip()
    path_match = re.search(
        r"([A-Za-z]:\\[^\s]+|/[^\s]+\.(?:pdf|docx?|pptx?|xlsx?|txt|md))",
        msg,
        flags=re.IGNORECASE,
    )
    if path_match:
        return path_match.group(1)
    return msg


def _enqueue_async_task_for_lane(
    *,
    lane: str,
    message: str,
    session_id: str | None,
    request_id: str | None,
    file_path: str | None,
    prefilled_fact: CapabilityFact | None,
) -> tuple[str, str]:
    sid = session_id or ""
    rid = request_id or ""
    if lane == "video":
        return task_plane_service.enqueue_video_background_task(
            url=_first_url(message),
            session_id=sid,
            request_id=rid,
            prefilled_fact=prefilled_fact,
        )
    if lane == "web":
        return task_plane_service.enqueue_web_heavy_fetch_task(
            url=_first_url(message),
            session_id=sid,
            request_id=rid,
            prefilled_fact=prefilled_fact,
        )
    if lane == "document":
        return task_plane_service.enqueue_document_ocr_task(
            file_path=_resolve_document_path(message=message, file_path=file_path),
            session_id=sid,
            request_id=rid,
        )
    return task_plane_service.enqueue_multi_source_research_task(
        user_query=message,
        session_id=sid,
        request_id=rid,
    )


def _async_answer_for_lane(lane: str) -> str:
    return _ASYNC_LANE_ANSWERS.get(
        lane,
        "这个请求已进入后台研究通道，我先返回任务状态。",
    )


def _async_next_action_for_lane(lane: str) -> str:
    return _ASYNC_NEXT_ACTIONS.get(
        lane,
        "复杂研究任务已后台化，系统会继续补料后产出总结。",
    )


def _async_capabilities_for_lane(lane: str) -> list[str]:
    return list(
        _ASYNC_CAPABILITIES.get(
            lane,
            ["capability.general.background_task"],
        )
    )


def assemble_async_pending_result(
    *,
    lane: str,
    task_id: str,
    queue_backend: str,
    answer: str,
    session_id: str | None,
    request_id: str | None,
    elapsed_ms: int,
    router_source: str,
    router_confidence: float,
    router_fallback: bool,
    router_decision_ms: int,
) -> ChatTurnResult:
    """Single assembler for async pending chat responses (§7.5)."""
    next_action = _async_next_action_for_lane(lane)
    extra: dict[str, Any] = build_common_exit_extra(
        extra_base={
            "lane": lane,
            EXIT_SIGNAL_PRIMARY_PATH: f"{lane}_async",
            "agno": True,
            "fast_path": False,
            "capabilities_called": _async_capabilities_for_lane(lane),
        },
        ingress=None,
        mode="async",
        executor_profile="async",
        progress_stage="queued",
        elapsed_ms=elapsed_ms,
    )
    extra.update({
        "next_action": next_action,
        "queue_backend": queue_backend,
        "router_lane": lane,
        "router_source": router_source,
        "router_confidence": router_confidence,
        "router_fallback": router_fallback,
        "router_decision_ms": router_decision_ms,
        "sla_deadline_ms": SLA_BUDGET_MS,
        "remaining_ms_at_answer_start": max(SLA_BUDGET_MS - elapsed_ms, 0),
        "agent_timings": {
            "session_snapshot_ms": 0,
            "main_ms": 0,
            "middle_ms": 0,
            "answer_ms": 0,
            "session_update_ms": 0,
            "extra_build_ms": 0,
            "total_ms": elapsed_ms,
        },
        "pending_agents": [lane],
        "completed_agents": [],
        "partial_answer_text": answer,
    })
    primary_path = f"{lane}_async"
    facts = TurnFacts(
        router_lane=lane,
        effective_mode="async",
        public_mode="async",
        executor_profile="async",
        pending_kind=PendingKind.PROCESSING_PENDING,
        primary_path_candidate=primary_path,
        async_pending=True,
        answer_type="async_pending",
    )
    return apply_turn_exit_to_chat_turn(
        build_chat_turn_result(
            answer=answer,
            session_id=session_id,
            request_id=request_id,
            task_id=task_id,
            answer_type="async_pending",
            extra=extra,
            elapsed_ms=elapsed_ms,
        ),
        facts=facts,
        effective_mode="async",
    )


def build_async_pending_result(
    *,
    message: str,
    lane: str,
    router_source: str,
    router_confidence: float,
    router_fallback: bool,
    router_decision_ms: int,
    session_id: str | None,
    request_id: str | None,
    elapsed_ms: int,
    file_path: str | None = None,
    prefilled_fact: CapabilityFact | None = None,
    existing_task_id: str | None = None,
    queue_backend: str | None = None,
) -> ChatTurnResult:
    """Enqueue (unless task already exists) and return unified async pending response."""
    if existing_task_id:
        task_id = str(existing_task_id).strip()
        backend = str(queue_backend or "existing").strip() or "existing"
    else:
        task_id, backend = _enqueue_async_task_for_lane(
            lane=lane,
            message=message,
            session_id=session_id,
            request_id=request_id,
            file_path=file_path,
            prefilled_fact=prefilled_fact,
        )
    answer = _async_answer_for_lane(lane)
    return assemble_async_pending_result(
        lane=lane,
        task_id=task_id,
        queue_backend=backend,
        answer=answer,
        session_id=session_id,
        request_id=request_id,
        elapsed_ms=elapsed_ms,
        router_source=router_source,
        router_confidence=router_confidence,
        router_fallback=router_fallback,
        router_decision_ms=router_decision_ms,
    )


def elapsed_ms_since(started_at: float) -> int:
    return format_ms((time.perf_counter() - started_at) * 1000)
