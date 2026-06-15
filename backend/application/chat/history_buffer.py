from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from threading import Lock

from agents.answer_agent import AnswerAgent
from agents.main_agent import MainAgent
from agents.middle_agent import MiddleAgent
from domain.session_types import PendingVideoText, PrevVideoRef, SessionApprovalHold


def history_key(session_id: str | None) -> str:
    return (session_id or "").strip() or "__default__"


def format_context(dq: deque[tuple[str, str]]) -> str | None:
    if not dq:
        return None
    parts: list[str] = []
    for u, a in dq:
        parts.append(f"用户：{u}\n助手：{a}")
    return "\n\n".join(parts)


@dataclass(frozen=True)
class ChatTurnDeps:
    histories: dict[str, deque[tuple[str, str]]]
    session_prev_video: dict[str, PrevVideoRef]
    session_pending_video: dict[str, PendingVideoText]
    lock: Lock
    main_agent: MainAgent
    middle_agent: MiddleAgent
    answer_agent: AnswerAgent
    run_basic_qa: Callable[..., str]
    path_fingerprint: Callable[..., str]
    nodes_contract: Callable[[list[str]], dict[str, str]]
    max_history_pairs: int = 6
    session_approval_hold: dict[str, SessionApprovalHold] = field(default_factory=dict)
