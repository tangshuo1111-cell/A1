from __future__ import annotations

from fastapi import APIRouter, Depends

from api.deps import verify_admin_optional
from storage import conversation_store

router = APIRouter(dependencies=[Depends(verify_admin_optional)])


@router.get("/{session_id}")
def get_session_summary(session_id: str) -> dict:
    rows = conversation_store.load_recent_for_session(session_id, limit=20)
    if not rows:
        from core.errors import AppError, ErrorCategory
        raise AppError(
            code="SESSION_NOT_FOUND",
            message="session not found or empty",
            category=ErrorCategory.NOT_FOUND,
        )
    return {
        "session_id": session_id,
        "turn_count": len(rows),
        "recent": [
            {
                "task_id": r.get("task_id"),
                "user_query": (r.get("user_query") or "")[:200],
                "task_status": r.get("task_status"),
                "answer_type": r.get("answer_type"),
            }
            for r in rows[-10:]
        ],
    }
