"""Collect turn-level facts for finalize_turn_exit (no routing or tool calls)."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from application.chat.chat_contracts import (
    ApprovalExitSignal,
    KbSufficiencyResult,
    MaterialSufficiencyResult,
    QualityGateResult,
    SharedMaterialPrepResult,
    normalize_task_status,
)
from application.chat.exit_signals import (
    material_sufficiency_signal_from_extra,
    mode_signal_from_extra,
    pending_kind_signal_from_extra,
    primary_path_signal_from_extra,
)
from application.chat.pending_kind import PendingKind, resolve_pending_kind_for_bundle


@dataclass(frozen=True)
class TurnFacts:
    router_lane: str = "general"
    ingress_mode: str = "fast"
    effective_mode: str = "fast"
    executor_profile: str = "fast"
    pending_kind: PendingKind = PendingKind.NONE
    hard_deadline_limited: bool = False
    bundle_pending_item_present: bool = False
    primary_path_candidate: str = ""
    answer_view_path: str = ""
    material_sufficiency: str | None = "sufficient"
    kb_sufficiency: KbSufficiencyResult | None = None
    material_result: MaterialSufficiencyResult | None = None
    quality_gate: QualityGateResult | None = None
    approval: ApprovalExitSignal | None = None
    async_pending: bool = False
    hard_failure: bool = False
    fast_delivery_forbidden: bool = False
    pipeline_ok: bool = True
    answer_type: str = ""
    limitations: tuple[str, ...] = ()
    shared_material: SharedMaterialPrepResult | None = None
    legacy_task_status: str | None = None
    public_mode: str | None = None


def quality_gate_from_extra(extra: dict[str, Any]) -> QualityGateResult | None:
    if "quality_gate.pass" not in extra and "quality_gate" not in extra:
        return None
    nested = extra.get("quality_gate")
    if isinstance(nested, dict):
        return QualityGateResult(
            pass_=bool(nested.get("pass", False)),
            upgrade_profile=bool(nested.get("upgrade_profile", False)),
            need_second_round=bool(nested.get("need_second_round", False)),
            need_more_material=bool(nested.get("need_more_material", False)),
            reason_codes=tuple(nested.get("reason_codes") or ()),
        )
    return QualityGateResult(
        pass_=bool(extra.get("quality_gate.pass", False)),
        upgrade_profile=bool(extra.get("quality_gate.upgrade_profile", False)),
        need_second_round=bool(extra.get("quality_gate.need_second_round", False)),
        need_more_material=bool(extra.get("quality_gate.need_more_material", False)),
        reason_codes=tuple(extra.get("quality_gate.reason_codes") or ()),
    )


def turn_facts_from_chat_result(
    result: dict[str, Any],
    *,
    ingress: Any | None = None,
    effective_mode: str | None = None,
    hard_deadline_limited: bool = False,
    bundle_pending_item_present: bool = False,
) -> TurnFacts:
    """Build TurnFacts from a legacy ChatTurnResult-shaped dict (pre-gate)."""
    extra = dict(result.get("extra") or {})
    answer_type = str(result.get("answer_type") or "")
    raw_pending = str(
        pending_kind_signal_from_extra(extra)
        or extra.get("pending_kind")
        or PendingKind.NONE.value
    ).strip()
    try:
        pending_kind = PendingKind(raw_pending)
    except ValueError:
        pending_kind = PendingKind.NONE

    router_lane = str(
        getattr(ingress, "lane", None) or extra.get("router_lane") or extra.get("lane") or "general"
    )
    ingress_mode = str(getattr(ingress, "mode", None) or "fast")
    extra_mode = str(mode_signal_from_extra(extra) or "").strip()
    if answer_type == "approval_blocked":
        eff = extra_mode or "blocked"
    elif answer_type == "async_pending":
        eff = extra_mode or str(effective_mode or "async")
    elif effective_mode is not None:
        eff = str(effective_mode)
    else:
        eff = extra_mode or ingress_mode or "fast"
    executor = str(extra.get("executor_profile") or eff)
    public_mode = extra_mode or eff

    approval: ApprovalExitSignal | None = None
    if answer_type == "approval_blocked" or extra.get("approval_gate.blocked"):
        approval = ApprovalExitSignal(blocked=True)
    elif answer_type == "commit_executed" or extra.get("approval_gate.executed"):
        approval = ApprovalExitSignal(
            commit_executed=True,
            commit_success=bool(extra.get("commit_success", result.get("pipeline_ok", True))),
        )

    legacy_status = str(result.get("task_status") or "")
    legacy_canon = normalize_task_status(legacy_status)
    async_pending = answer_type == "async_pending" or (
        legacy_canon == "pending"
        and answer_type in {"fast_pending", "async_pending"}
    )
    if async_pending and pending_kind == PendingKind.NONE:
        pending_kind = PendingKind.PROCESSING_PENDING

    hard_failure = legacy_canon == "failed" and answer_type != "commit_executed"

    primary_candidate = str(primary_path_signal_from_extra(extra) or "").strip()
    return TurnFacts(
        router_lane=router_lane,
        ingress_mode=ingress_mode,
        effective_mode=eff,
        executor_profile=executor,
        pending_kind=pending_kind,
        hard_deadline_limited=hard_deadline_limited,
        bundle_pending_item_present=bundle_pending_item_present,
        primary_path_candidate=primary_candidate,
        answer_view_path=primary_candidate,
        material_sufficiency=str(material_sufficiency_signal_from_extra(extra) or "sufficient"),
        quality_gate=quality_gate_from_extra(extra),
        approval=approval,
        async_pending=async_pending and answer_type != "approval_blocked",
        hard_failure=hard_failure,
        fast_delivery_forbidden=False,
        pipeline_ok=bool(result.get("pipeline_ok", True)),
        answer_type=answer_type,
        limitations=tuple(extra.get("limitations") or ()),
        legacy_task_status=legacy_status or None,
        public_mode=public_mode,
    )


def build_complex_turn_facts(
    *,
    bundle: Any,
    extra: dict[str, Any],
    ingress: Any,
    effective_mode: str,
    history_snapshot: Any,
    session_pending_kind: Any,
    hard_deadline_limited: bool,
    public_mode: str,
    executor_profile: str,
    primary_path_candidate: str,
    material_sufficiency: str,
    quality_gate: QualityGateResult | None,
    limitations: tuple[str, ...],
) -> TurnFacts:
    """Build TurnFacts for the complex path without pre-resolving final exit status."""
    resolved = resolve_pending_kind_for_bundle(
        bundle=bundle,
        history_snapshot=history_snapshot,
        session_pending_kind=session_pending_kind,
    )
    pending_kind = resolved if resolved is not None else PendingKind.NONE
    return TurnFacts(
        router_lane=str(getattr(ingress, "lane", "general") or "general"),
        ingress_mode=str(getattr(ingress, "mode", "fast") or "fast"),
        effective_mode=effective_mode,
        public_mode=public_mode,
        executor_profile=executor_profile,
        pending_kind=pending_kind,
        hard_deadline_limited=hard_deadline_limited,
        bundle_pending_item_present=getattr(bundle, "pending_item", None) is not None,
        primary_path_candidate=primary_path_candidate,
        answer_view_path=primary_path_candidate,
        material_sufficiency=material_sufficiency,
        quality_gate=quality_gate,
        answer_type="basic_agno",
        limitations=limitations,
        legacy_task_status=None,
    )


def lift_background_task_exit(
    *,
    facts: TurnFacts,
    extra: dict[str, Any],
    bundle: Any | None = None,
) -> tuple[TurnFacts, dict[str, Any], str]:
    """Promote background task id to async-pending exit facts (complex path only)."""
    from application.chat.chat_contracts import resolve_background_task_id

    background_task_id = resolve_background_task_id(extra=extra, bundle=bundle)
    if not background_task_id:
        return facts, extra, ""
    extra_out = dict(extra)
    extra_out.setdefault(
        "next_action",
        "后台任务处理中，请轮询 /tasks/{task_id}/result 获取完整结果。",
    )
    pending = (
        facts.pending_kind
        if facts.pending_kind != PendingKind.NONE
        else PendingKind.PROCESSING_PENDING
    )
    return (
        replace(
            facts,
            async_pending=True,
            pending_kind=pending,
            legacy_task_status="pending",
            answer_type="async_pending",
        ),
        extra_out,
        background_task_id,
    )


def _has_real_task_evidence(extra: dict[str, Any]) -> bool:
    from application.chat.chat_contracts import resolve_background_task_id

    if resolve_background_task_id(extra=extra):
        return True
    if str(extra.get("task_id") or "").strip():
        return True
    raw_pending = str(
        pending_kind_signal_from_extra(extra) or extra.get("pending_kind") or ""
    ).strip().lower()
    return bool(raw_pending and raw_pending != PendingKind.NONE.value)


EMPTY_CONTEXT_FOLLOWUP_ANSWER = (
    "当前没有可承接的上文。请补充你想继续的内容，或重新说明问题。"
)


_EMPTY_CONTEXT_FOLLOWUP_EXPLICIT = (
    "继续刚才",
    "刚才那个",
    "刚才这",
    "上一轮",
    "上一次",
    "保存刚才",
    "继续处理",
    "继续总结",
    "继续分析",
    "接着说",
    "接着说",
    "接着讲",
    "接着分析",
    "接着回答",
    "接着总结",
    "再说一次",
)


def _is_empty_context_followup_candidate(user_message: str) -> bool:
    """Follow-up continuation without prior session context (stricter than agent anchor signal)."""
    from domain.session_types import looks_like_followup_reference

    msg = (user_message or "").strip()
    if not msg or not looks_like_followup_reference(msg):
        return False
    lower = msg.lower()
    if "http://" in lower or "https://" in lower:
        return False
    if any(
        token in msg
        for token in (
            "总结这个网页",
            "总结这个链接",
            "分析这个文档",
            "处理这个视频",
            "请总结这个",
            "请分析这个",
            "请处理这个",
        )
    ):
        return False
    return any(token in msg for token in _EMPTY_CONTEXT_FOLLOWUP_EXPLICIT)


def build_empty_context_followup_answer() -> str:
    return EMPTY_CONTEXT_FOLLOWUP_ANSWER


def _has_carryover_session_facts(
    *,
    extra: dict[str, Any],
    pending_video: Any | None,
    prev_video_ref: Any | None,
    v13_text_content: str | None = None,
    v13_file_content: str | bytes | None = None,
    stitch_applied: bool = False,
) -> bool:
    if pending_video is not None:
        return True
    if prev_video_ref is not None:
        return True
    if _has_real_task_evidence(extra):
        return True
    if (v13_text_content or "").strip() or v13_file_content is not None:
        return True
    if stitch_applied or extra.get("turn_stitch.applied"):
        return True
    if int(extra.get("v15_temporary_materials_count") or 0) > 0:
        return True
    if int(extra.get("web_evidence_chars") or 0) > 0:
        return True
    if str(extra.get("web_primary_source") or "").strip():
        return True
    if int(extra.get("v15_retrieved_chunks_count") or 0) > 0:
        return True
    return False


def lift_empty_context_followup(
    *,
    facts: TurnFacts,
    extra: dict[str, Any],
    user_message: str,
    history_snapshot: Any | None,
    pending_video: Any | None = None,
    prev_video_ref: Any | None = None,
    v13_text_content: str | None = None,
    v13_file_content: str | bytes | None = None,
    stitch_applied: bool = False,
) -> tuple[TurnFacts, dict[str, Any]]:
    """Promote empty-session follow-up reference to blocked clarify exit facts."""
    if not _is_empty_context_followup_candidate(user_message):
        return facts, extra
    if history_snapshot is not None and history_snapshot.has_context:
        return facts, extra
    if _has_carryover_session_facts(
        extra=extra,
        pending_video=pending_video,
        prev_video_ref=prev_video_ref,
        v13_text_content=v13_text_content,
        v13_file_content=v13_file_content,
        stitch_applied=stitch_applied,
    ):
        return facts, extra

    extra_out = dict(extra)
    extra_out.update(
        {
            "empty_context_followup": True,
            "followup_detected": True,
            "history_used": False,
        }
    )
    return (
        replace(
            facts,
            approval=ApprovalExitSignal(blocked=True),
            answer_type="approval_blocked",
            effective_mode="blocked",
            public_mode="blocked",
            executor_profile="blocked",
            primary_path_candidate="approval_gate",
            pipeline_ok=False,
            async_pending=False,
            legacy_task_status="blocked",
        ),
        extra_out,
    )


def lift_session_approval_hold(
    *,
    facts: TurnFacts,
    extra: dict[str, Any],
    approval_hold: Any | None,
    user_message: str,
) -> tuple[TurnFacts, dict[str, Any]]:
    """Promote session approval hold + task-status inquiry to approval-blocked facts."""
    from domain.session_types import SessionApprovalHold, looks_like_task_status_inquiry

    if not isinstance(approval_hold, SessionApprovalHold) or not approval_hold.blocked:
        return facts, extra
    if not looks_like_task_status_inquiry(user_message):
        return facts, extra
    if _has_real_task_evidence(extra):
        return facts, extra

    extra_out = dict(extra)
    extra_out.update(
        {
            "approval_gate.blocked": True,
            "approval_gate.kind": approval_hold.kind,
            "approval_gate.reason": approval_hold.reason or "await_user_confirm",
        }
    )
    return (
        replace(
            facts,
            approval=ApprovalExitSignal(blocked=True),
            answer_type="approval_blocked",
            effective_mode="blocked",
            public_mode="blocked",
            executor_profile="blocked",
            primary_path_candidate="approval_gate",
            pipeline_ok=False,
            async_pending=False,
        ),
        extra_out,
    )
