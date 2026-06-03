"""User-approval gate — separate from quality_gate and feedback_gate (v1 scope)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

ApprovalKind = Literal["pending_commit", "long_video_asr", "heavy_processing"]

_COMMIT_HINTS = ("保存", "入库", "存进知识库", "存入知识库", "commit", "确认保存")


def is_commit_intent(message: str) -> bool:
    msg = (message or "").strip().lower()
    if not msg:
        return False
    return any(hint in msg for hint in _COMMIT_HINTS)


@dataclass(frozen=True)
class ApprovalGateResult:
    required: bool = False
    kind: ApprovalKind | None = None
    reason: str = ""
    blocked: bool = False


def evaluate_pending_commit(*, commit_requested: bool, has_pending_item: bool) -> ApprovalGateResult:
    if commit_requested and not has_pending_item:
        return ApprovalGateResult(
            required=True,
            kind="pending_commit",
            reason="no_pending_item",
            blocked=True,
        )
    if commit_requested:
        return ApprovalGateResult(required=True, kind="pending_commit", reason="await_user_confirm")
    return ApprovalGateResult()


def evaluate_long_video_confirmation(
    *,
    confirm_long_asr: bool,
    requires_confirmation: bool,
    source_type: str = "",
) -> ApprovalGateResult:
    if not requires_confirmation:
        return ApprovalGateResult()
    if confirm_long_asr:
        return ApprovalGateResult(required=True, kind="long_video_asr", reason="confirmed")
    return ApprovalGateResult(
        required=True,
        kind="long_video_asr",
        reason="await_user_confirm",
        blocked=True,
    )


def evaluate_heavy_processing_confirmation(
    *,
    asks_background: bool,
    heavy_signal: bool,
    user_confirmed: bool = False,
) -> ApprovalGateResult:
    if not heavy_signal:
        return ApprovalGateResult()
    if user_confirmed or asks_background:
        return ApprovalGateResult(required=True, kind="heavy_processing", reason="confirmed")
    return ApprovalGateResult(
        required=True,
        kind="heavy_processing",
        reason="await_user_confirm",
        blocked=True,
    )


def merge_approval_results(*results: ApprovalGateResult) -> ApprovalGateResult:
    blocked = next((r for r in results if r.blocked), None)
    if blocked is not None:
        return blocked
    required = next((r for r in results if r.required), None)
    return required or ApprovalGateResult()


def approval_trace_extra(result: ApprovalGateResult) -> dict[str, Any]:
    if not result.required:
        return {}
    return {
        "approval_gate.required": True,
        "approval_gate.kind": result.kind or "",
        "approval_gate.reason": result.reason,
        "approval_gate.blocked": result.blocked,
    }
