"""User-approval gate — separate from quality_gate and feedback_gate (v1 scope)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

ApprovalKind = Literal["pending_commit", "long_video_asr", "heavy_processing"]

_COMMIT_HINTS = ("保存", "入库", "存进知识库", "存入知识库", "commit", "确认保存")

# 明确的祈使保存短语：命中即视为真实保存命令，始终判 commit（保护真实保存意图不被收窄误伤）。
_IMPERATIVE_SAVE = (
    "保存到",
    "保存进",
    "保存下来",
    "保存一下",
    "保存这",
    "保存它",
    "保存该",
    "存入",
    "存进",
    "存到",
    "存起来",
    "收录到",
    "入库到",
    "帮我保存",
    "帮我存",
    "请保存",
    "确认保存",
)

# 分析/比较语境标记：命中 >=2 个时，视为“讨论入库/保存策略”而非“执行入库命令”。
_DISCUSSION_MARKERS = (
    "评估",
    "对比",
    "比较",
    "分析",
    "影响",
    "区别",
    "差异",
    "优缺点",
    "优劣",
    "策略",
    "权衡",
    "取舍",
    "维度",
    "推荐",
    "如何",
    "怎样",
    "是否",
    "为什么",
    "建议",
)

# 书名号/引号包裹片段：命令词出现在其中说明它是“被讨论的对象”，而非命令本身。
_QUOTED_SEGMENT = re.compile(r"[「『\u201c\u2018《\"']([^」』\u201d\u2019》\"']{0,40})[」』\u201d\u2019》\"']")


def _commit_in_quotes(msg: str) -> bool:
    return any(
        any(hint in seg for hint in _COMMIT_HINTS) for seg in _QUOTED_SEGMENT.findall(msg)
    )


def _discussion_score(msg: str) -> int:
    return sum(1 for marker in _DISCUSSION_MARKERS if marker in msg)


def is_commit_intent(message: str) -> bool:
    """是否为“提交入库/保存”命令意图。

    收窄 KI-V1-002：旧实现裸子串 `any(hint in msg)`，导致“评估『自动入库』与『确认后保存』
    两种策略的影响”这类分析题被误判为提交命令、在无 pending 资料时被 approval blocked。
    收窄规则（不改 ApprovalGateResult 契约，只减少误判）：
      1) 命中明确祈使保存短语 → 始终判 commit（保护真实保存）；
      2) 命令词被书名号/引号包裹，或句中含 >=2 个分析/比较标记 → 视为讨论，不判 commit；
      3) 其余维持原裸子串判定。
    """
    msg = (message or "").strip()
    if not msg:
        return False
    low = msg.lower()
    if not any(hint in low for hint in _COMMIT_HINTS):
        return False
    if any(phrase in msg for phrase in _IMPERATIVE_SAVE):
        return True
    # 命令词被引号包裹（作讨论对象），或含 >=2 个分析/比较标记 → 判为讨论而非提交命令
    return not (_commit_in_quotes(msg) or _discussion_score(msg) >= 2)


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
