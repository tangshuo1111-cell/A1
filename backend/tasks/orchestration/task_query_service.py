"""公开任务查询语义层：把存储行规范化为稳定 API 契约。"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from application.chat.pending_kind import PendingKind
from config.settings import settings
from storage import conversation_store, task_job_store
from storage.task_job_constants import (
    STATUS_CANCELLED,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_QUEUED,
    STATUS_RUNNING,
    STATUS_SUCCEEDED,
    STATUS_TIMEOUT,
)

PUBLIC_STATUS_QUEUED = "queued"
PUBLIC_STATUS_RUNNING = "running"
PUBLIC_STATUS_PARTIAL = "partial"
PUBLIC_STATUS_SUCCEEDED = "succeeded"
PUBLIC_STATUS_FAILED = "failed"
PUBLIC_STATUS_EXPIRED = "expired"
PUBLIC_STATUS_CANCELLED = "cancelled"


def pending_kind_for_public_status(public_status: str) -> str:
    """Map task API status to chat PendingKind (§5.4 / AS3)."""
    if public_status in {PUBLIC_STATUS_QUEUED, PUBLIC_STATUS_RUNNING}:
        return PendingKind.PROCESSING_PENDING.value
    if public_status == PUBLIC_STATUS_PARTIAL:
        return PendingKind.PARTIAL_PENDING.value
    return PendingKind.NONE.value


def _parse_iso(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _result_ttl_seconds() -> int:
    return max(int(settings.task_result_ttl_seconds or 0), 0)


def _expires_at(task_row: dict[str, Any]) -> datetime | None:
    ttl = _result_ttl_seconds()
    if ttl <= 0:
        return None
    base = _parse_iso(task_row.get("finished_at")) or _parse_iso(task_row.get("updated_at"))
    if base is None:
        return None
    return base + timedelta(seconds=ttl)


def is_task_result_expired(task_row: dict[str, Any]) -> bool:
    exp = _expires_at(task_row)
    if exp is None:
        return False
    return datetime.now(UTC) >= exp


def normalize_public_task_status(task_row: dict[str, Any]) -> str:
    raw_status = str(task_row.get("status") or "").strip().lower()
    if not raw_status:
        return PUBLIC_STATUS_RUNNING
    if raw_status in (STATUS_PENDING, STATUS_QUEUED):
        return PUBLIC_STATUS_QUEUED
    if raw_status == STATUS_RUNNING:
        return PUBLIC_STATUS_RUNNING
    if raw_status == STATUS_CANCELLED:
        return PUBLIC_STATUS_CANCELLED
    if raw_status in (STATUS_FAILED, STATUS_TIMEOUT):
        return PUBLIC_STATUS_FAILED
    if raw_status == STATUS_SUCCEEDED:
        if is_task_result_expired(task_row):
            return PUBLIC_STATUS_EXPIRED
        result_summary = task_row.get("result_summary") or {}
        result_status = str((result_summary or {}).get("status") or "").strip().lower()
        if result_status == PUBLIC_STATUS_PARTIAL:
            return PUBLIC_STATUS_PARTIAL
        if task_row.get("result_pending_id") and not task_row.get("result_source_id"):
            return PUBLIC_STATUS_PARTIAL
        return PUBLIC_STATUS_SUCCEEDED
    return raw_status


_TASK_RESULT_PLACEHOLDER_MARKERS = (
    "【测试回答·fake桩】",
    "本回答由 fake llm 桩生成",
    "后台任务处理中",
    "请轮询 /tasks/",
)


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _looks_like_placeholder_answer(text: str) -> bool:
    normalized = _normalize_text(text).lower()
    if not normalized:
        return False
    if any(marker in normalized for marker in _TASK_RESULT_PLACEHOLDER_MARKERS):
        return True
    return False


def _select_public_result_answer(
    *,
    result_summary: dict[str, Any],
    turn: dict[str, Any] | None,
) -> str | None:
    final_answer = _normalize_text((result_summary or {}).get("final_answer"))
    if final_answer:
        return final_answer
    turn_answer = _normalize_text((turn or {}).get("answer"))
    if not turn_answer or _looks_like_placeholder_answer(turn_answer):
        return None
    return turn_answer


def _normalize_task_row(task_row: dict[str, Any]) -> dict[str, Any]:
    public_status = normalize_public_task_status(task_row)
    exp = _expires_at(task_row)
    metadata = task_row.get("metadata") or {}
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except json.JSONDecodeError:
            metadata = {}
    elif not isinstance(metadata, dict):
        metadata = {}
    enqueue_to_finish_ms = 0
    enqueued_at_ms = int(metadata.get("enqueued_at_ms") or 0)
    finished_at = _parse_iso(task_row.get("finished_at"))
    if enqueued_at_ms > 0 and finished_at is not None:
        enqueue_to_finish_ms = max(int(finished_at.timestamp() * 1000) - enqueued_at_ms, 0)
    result_summary = task_row.get("result_summary") or {}
    diagnostics = metadata.get("video_failure_diagnostics") if isinstance(metadata, dict) else None
    return {
        "task_id": str(task_row.get("task_id") or ""),
        "status": public_status,
        "pending_kind": pending_kind_for_public_status(public_status),
        "raw_status": str(task_row.get("status") or ""),
        "task_type": str(task_row.get("task_type") or ""),
        "source_type": str(task_row.get("source_type") or ""),
        "stage": str(task_row.get("stage") or task_row.get("current_node") or ""),
        "progress": float(task_row.get("progress") or 0.0),
        "session_id": task_row.get("session_id"),
        "request_id": task_row.get("request_id"),
        "created_at": task_row.get("created_at"),
        "updated_at": task_row.get("updated_at"),
        "started_at": task_row.get("started_at"),
        "finished_at": task_row.get("finished_at"),
        "duration_ms": float(task_row.get("duration_ms") or 0.0),
        "error_code": str(task_row.get("error_code") or ""),
        "failure_reason": str(task_row.get("failure_reason") or ""),
        "next_action_hint": str(task_row.get("next_action_hint") or ""),
        "result_pending_id": str(task_row.get("result_pending_id") or ""),
        "result_source_id": str(task_row.get("result_source_id") or ""),
        "result_ttl_seconds": _result_ttl_seconds(),
        "expires_at": exp.isoformat() if exp is not None else None,
        "payload_version": int(metadata.get("payload_version") or 1),
        "queue_backend": str(metadata.get("queue_backend") or ""),
        "retry_count": int(metadata.get("retry_count") or 0),
        "task_enqueue_to_finish_ms": enqueue_to_finish_ms,
        "result_status": str((result_summary or {}).get("status") or "").strip().lower(),
        "diagnostics": diagnostics if isinstance(diagnostics, dict) else None,
    }


def get_task_status_payload(task_id: str) -> dict[str, Any] | None:
    row = task_job_store.get_job(task_id)
    if row is None:
        return None
    payload = _normalize_task_row(row)
    payload["result_ready"] = payload["status"] in {
        PUBLIC_STATUS_SUCCEEDED,
        PUBLIC_STATUS_PARTIAL,
    }
    return payload


def get_task_result_payload(task_id: str) -> dict[str, Any] | None:
    row = task_job_store.get_job(task_id)
    if row is None:
        return None

    payload = _normalize_task_row(row)
    turn = conversation_store.get_turn_by_task_id(task_id)
    result_summary = row.get("result_summary") if isinstance(row.get("result_summary"), dict) else {}

    ready = payload["status"] in {
        PUBLIC_STATUS_SUCCEEDED,
        PUBLIC_STATUS_PARTIAL,
        PUBLIC_STATUS_FAILED,
        PUBLIC_STATUS_EXPIRED,
        PUBLIC_STATUS_CANCELLED,
    }
    payload["ready"] = ready
    payload["result"] = None
    payload["error"] = None

    if payload["status"] in {PUBLIC_STATUS_SUCCEEDED, PUBLIC_STATUS_PARTIAL}:
        public_answer = _select_public_result_answer(
            result_summary=result_summary,
            turn=turn,
        )
        payload["result"] = {
            "answer": public_answer,
            "final_answer": public_answer,
            "transcript_text": (result_summary or {}).get("transcript_text"),
            "answer_type": (turn or {}).get("answer_type"),
            "task_status": (turn or {}).get("task_status"),
            "user_visible_status": (turn or {}).get("user_visible_status"),
            "has_insufficient_info_notice": bool(
                str((turn or {}).get("has_insufficient_info_notice") or "0") in {"1", "true", "True"}
            ),
            "summary": result_summary,
            "result_pending_id": payload["result_pending_id"],
            "result_source_id": payload["result_source_id"],
            "draft": bool((result_summary or {}).get("draft")),
            "draft_limitations": list((result_summary or {}).get("draft_limitations") or []),
        }
    elif payload["status"] in {PUBLIC_STATUS_FAILED, PUBLIC_STATUS_CANCELLED, PUBLIC_STATUS_EXPIRED}:
        payload["error"] = {
            "code": payload["error_code"] or (
                "task_expired"
                if payload["status"] == PUBLIC_STATUS_EXPIRED
                else "task_not_available"
            ),
            "message": payload["failure_reason"] or (
                "任务结果已过期"
                if payload["status"] == PUBLIC_STATUS_EXPIRED
                else "任务未成功完成"
            ),
            "diagnostics": payload.get("diagnostics"),
        }

    return payload
