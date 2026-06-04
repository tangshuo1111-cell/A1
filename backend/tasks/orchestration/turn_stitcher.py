"""Inter-turn stitching — persist completed async task summaries for follow-up turns (§6.6)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from config.feature_flags import is_enabled
from storage import task_job_store


@dataclass(frozen=True)
class TaskStitchSlot:
    task_id: str
    summary_text: str
    lane: str
    attached_at: str


def turn_stitcher_active() -> bool:
    return is_enabled("ENABLE_TURN_STITCHER") and is_enabled("ENABLE_ASYNC_CONTROL_PLANE_V2")


def _slot_payload(slot: TaskStitchSlot, *, consumed: bool = False) -> dict[str, Any]:
    return {
        "task_id": slot.task_id,
        "summary_text": slot.summary_text,
        "lane": slot.lane,
        "attached_at": slot.attached_at,
        "consumed": consumed,
        "consumed_at": datetime.now().isoformat(timespec="seconds") if consumed else "",
    }


def _slot_from_metadata(metadata: dict[str, Any] | None) -> TaskStitchSlot | None:
    payload = dict((metadata or {}).get("turn_stitch_slot") or {})
    if not payload or bool(payload.get("consumed")):
        return None
    task_id = str(payload.get("task_id") or "").strip()
    summary_text = str(payload.get("summary_text") or "").strip()
    if not task_id or not summary_text:
        return None
    return TaskStitchSlot(
        task_id=task_id,
        summary_text=summary_text,
        lane=str(payload.get("lane") or "video"),
        attached_at=str(payload.get("attached_at") or ""),
    )


def _mark_slot_consumed(task_id: str, slot: TaskStitchSlot) -> None:
    task_job_store.update_task_async_metadata(
        task_id,
        metadata={"turn_stitch_slot": _slot_payload(slot, consumed=True)},
    )


def _find_task_slot(session_id: str | None) -> tuple[str, TaskStitchSlot] | None:
    sid = (session_id or "").strip()
    if not sid:
        return None
    for row in task_job_store.list_recent_jobs(limit=200):
        if str(row.get("session_id") or "").strip() != sid:
            continue
        slot = _slot_from_metadata(row.get("metadata") if isinstance(row.get("metadata"), dict) else None)
        if slot is not None:
            return str(row.get("task_id") or ""), slot
    return None


def attach_completed_task_to_history(
    *,
    session_id: str,
    task_id: str,
    summary_text: str,
    lane: str = "video",
) -> None:
    """Persist async task summary for the next chat turn in this session."""
    if not turn_stitcher_active():
        return
    sid = (session_id or "").strip()
    summary = (summary_text or "").strip()
    if not sid or not summary:
        return
    slot = TaskStitchSlot(
        task_id=str(task_id or "").strip(),
        summary_text=summary,
        lane=str(lane or "video"),
        attached_at=datetime.now().isoformat(timespec="seconds"),
    )
    if task_job_store.get_job(slot.task_id) is None:
        return
    task_job_store.update_task_async_metadata(
        slot.task_id,
        metadata={"turn_stitch_slot": _slot_payload(slot, consumed=False)},
    )


def peek_stitch_slot(session_id: str | None) -> TaskStitchSlot | None:
    found = _find_task_slot(session_id)
    return found[1] if found is not None else None


def consume_stitch_slot(session_id: str | None) -> TaskStitchSlot | None:
    found = _find_task_slot(session_id)
    if found is None:
        return None
    task_id, slot = found
    _mark_slot_consumed(task_id, slot)
    return slot


def stitch_slot_to_pending_video(slot: TaskStitchSlot) -> Any:
    from agents.history_context import PendingVideoText

    return PendingVideoText(
        text=slot.summary_text,
        title=f"后台任务 {slot.task_id}",
        source_url=f"task://{slot.task_id}",
        source_basename=slot.task_id,
        duration_sec=0.0,
        text_source="asr",
    )


def stitch_slot_to_inline_material(slot: TaskStitchSlot) -> str:
    """web / document 异步任务摘要：注入 v13 内联材料供下一轮 Middle/Answer 消费。"""
    lane = (slot.lane or "web").strip() or "web"
    body = (slot.summary_text or "").strip()
    if not body:
        return ""
    return (
        f"【以下为已完成的后台任务摘要（{lane}）】\n"
        f"{body}\n"
        f"【摘要结束】"
    )


def maybe_attach_task_result(
    *,
    session_id: str,
    task_id: str,
    result_summary: dict[str, Any],
    lane: str,
) -> None:
    """Helper for workers after mark_task_succeeded."""
    final_answer = str((result_summary or {}).get("final_answer") or "").strip()
    if not final_answer:
        return
    attach_completed_task_to_history(
        session_id=session_id,
        task_id=task_id,
        summary_text=final_answer,
        lane=lane,
    )


def reset_stitch_slots_for_tests() -> None:
    for row in task_job_store.list_recent_jobs(limit=200):
        task_id = str(row.get("task_id") or "").strip()
        metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else None
        slot = _slot_from_metadata(metadata)
        if task_id and slot is not None:
            _mark_slot_consumed(task_id, slot)
