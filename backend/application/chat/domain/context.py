"""Request-scoped turn context — immutable inputs and session handles."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from application.chat.budget_clock import BudgetClock


@dataclass(frozen=True)
class UploadMeta:
    file_content: str | bytes | None = None
    text_content: str | None = None
    title: str | None = None


@dataclass(frozen=True)
class TurnFlags:
    use_knowledge: bool = False
    confirm_long_web_video_asr: bool = False


@dataclass(frozen=True)
class TurnContext:
    """Canonical request context for one chat turn (Round 1+)."""

    user_input: str
    session_id: str | None
    request_id: str | None = None
    upload: UploadMeta = field(default_factory=UploadMeta)
    flags: TurnFlags = field(default_factory=TurnFlags)
    clock: BudgetClock | None = None
    pending_refs: dict[str, Any] = field(default_factory=dict)
    task_refs: dict[str, Any] = field(default_factory=dict)
