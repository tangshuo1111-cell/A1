from __future__ import annotations

from fastapi import APIRouter, Depends

from api.api_errors import raise_not_found
from api.deps import verify_admin_optional
from api.schemas_http import SessionSummaryResponse, SessionTurnSummary
from storage import conversation_store

router = APIRouter(dependencies=[Depends(verify_admin_optional)])


@router.get("/{session_id}", response_model=SessionSummaryResponse)
def get_session_summary(session_id: str) -> SessionSummaryResponse:
    rows = conversation_store.load_recent_for_session(session_id, limit=20)
    if not rows:
        raise_not_found("SESSION_NOT_FOUND", "session not found or empty")
    recent = [
        SessionTurnSummary(
            task_id=r.get("task_id"),
            user_query=(r.get("user_query") or "")[:200],
            task_status=r.get("task_status"),
            answer_type=r.get("answer_type"),
        )
        for r in rows[-10:]
    ]
    return SessionSummaryResponse(
        ok=True,
        session_id=session_id,
        turn_count=len(rows),
        recent=recent,
    )
