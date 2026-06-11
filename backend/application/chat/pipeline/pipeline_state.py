"""Mutable runtime state shared across turn pipeline stages (Round 3)."""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from application.chat.budget_clock import BudgetClock
from application.chat.domain.context import TurnContext
from application.chat.turn_state_machine import TurnStateBundle
from domain.session_types import PendingVideoText, PrevVideoRef, SessionHistorySnapshot


@dataclass
class TurnPipelineState:
    ctx: TurnContext
    deps: Any
    t0: float = field(default_factory=time.perf_counter)
    budget_clock: BudgetClock | None = None
    deadline_at: float = 0.0
    key: str = ""
    timing: dict[str, int] = field(default_factory=dict)
    turn_cache_token: Any = None
    stitch_applied: bool = False
    stitch_lane: str | None = None
    hist: deque = field(default_factory=deque)
    context_block: str | None = None
    prev_video_ref: PrevVideoRef | None = None
    pending_video: PendingVideoText | None = None
    history_snapshot: SessionHistorySnapshot | None = None
    ingress: Any = None
    turn_state: TurnStateBundle | None = None
    effective_mode: str = "fast"
    arbitrator_reason: str = ""
    arbitrator_trace: list[dict[str, Any]] = field(default_factory=list)
    session_pending_kind: Any = None
    shared_prep: Any = None
    message: str = ""
    session_id: str | None = None
    request_id: str | None = None
    use_knowledge: bool = False
    v13_file_content: str | bytes | None = None
    v13_text_content: str | None = None
    v13_title: str | None = None
    confirm_long_web_video_asr: bool = False
