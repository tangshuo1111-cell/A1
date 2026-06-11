"""Thin orchestrator for user-approval gate (v1: pending commit + long video / heavy)."""

from __future__ import annotations

from typing import Any

from application.chat.approval_gate import (
    ApprovalGateResult,
    approval_trace_extra,
    evaluate_heavy_processing_confirmation,
    evaluate_long_video_confirmation,
    evaluate_pending_commit,
    is_commit_intent,
    merge_approval_results,
)
from application.chat.chat_contracts import ApprovalExitSignal
from application.chat.exit_signals import (
    EXIT_SIGNAL_PRIMARY_PATH,
    set_material_sufficiency_signal,
    set_mode_signal,
)
from application.chat.material_flow import material_trace_for_extra
from application.chat.turn_exit_extra import build_common_exit_extra
from application.chat.turn_exit_gate import apply_turn_exit_to_chat_turn
from application.chat.turn_facts import TurnFacts
from application.chat.turn_response_builder import build_chat_turn_result
from application.ingress.request_classifier import classify_request
from config.feature_flags import approval_gate_active


def evaluate_turn_approval(
    *,
    message: str,
    session_id: str | None,
    confirm_long_web_video_asr: bool,
    use_knowledge: bool,
    v13_file_content: str | bytes | None = None,
    v13_text_content: str | None = None,
) -> ApprovalGateResult:
    if not approval_gate_active():
        return ApprovalGateResult()

    signals = classify_request(
        message=message,
        use_knowledge=use_knowledge,
        v13_file_content=v13_file_content,
        v13_text_content=v13_text_content,
    )

    commit_requested = is_commit_intent(message)
    has_pending = False
    pending_count = 0
    if commit_requested and session_id:
        from services.capabilities.knowledge import pending_ingestion_service

        pending_items = pending_ingestion_service.list_pending(session_id, only_committable=True)
        pending_count = len(pending_items)
        has_pending = pending_count > 0

    results = [
        evaluate_pending_commit(commit_requested=commit_requested, has_pending_item=has_pending),
        evaluate_long_video_confirmation(
            confirm_long_asr=confirm_long_web_video_asr,
            requires_confirmation=(
                signals.has_long_video_hint
                and (signals.has_video_url or signals.has_video_attachment)
                and not confirm_long_web_video_asr
            ),
        ),
        evaluate_heavy_processing_confirmation(
            asks_background=signals.asks_background_processing,
            heavy_signal=(
                signals.asks_background_processing
                and (
                    signals.has_video_url
                    or signals.has_video_attachment
                    or bool(v13_file_content)
                )
            ),
            user_confirmed=confirm_long_web_video_asr,
        ),
    ]
    result = merge_approval_results(*results)
    if result.required and result.kind == "pending_commit" and has_pending:
        return ApprovalGateResult(
            required=True,
            kind="pending_commit",
            reason="execute_commit",
            blocked=False,
        )
    return result


def build_approval_blocked_answer(result: ApprovalGateResult) -> str:
    if result.kind == "pending_commit" and result.reason == "no_pending_item":
        return "当前会话没有可保存的 pending 资料。请先上传或解析资料，再确认入库。"
    if result.kind == "long_video_asr":
        return (
            "该视频可能需较长 ASR 处理。请确认后继续"
            "（请求体设置 confirm_long_web_video_asr=true），或改用后台异步处理。"
        )
    if result.kind == "heavy_processing":
        return "该请求涉及重处理，请明确确认后台处理（消息中含「后台/异步」）或携带确认参数后再试。"
    return "该操作需要用户确认后才能继续。"


def build_approval_blocked_turn_result(
    *,
    result: ApprovalGateResult,
    message: str,
    session_id: str | None,
    request_id: str | None,
    elapsed_ms: int,
    ingress: Any | None = None,
    extra_base: dict[str, Any] | None = None,
    pending_count: int = 0,
) -> dict[str, Any]:
    extra = build_common_exit_extra(
        extra_base={
            "lane": "approval_gate",
            EXIT_SIGNAL_PRIMARY_PATH: "approval_gate",
            **(extra_base or {}),
        },
        ingress=ingress,
        mode="blocked",
        executor_profile="blocked",
        progress_stage="approval_required",
        elapsed_ms=elapsed_ms,
    )
    extra.update(approval_trace_extra(result))
    extra.update(
        material_trace_for_extra(
            approval_kind=result.kind,
            pending_count=pending_count,
            executor_profile="blocked",
        )
    )
    set_mode_signal(extra, "blocked")
    set_material_sufficiency_signal(extra, str(extra.get("material_sufficiency") or "sufficient"))
    facts = TurnFacts(
        router_lane=str(getattr(ingress, "lane", "general") or "general"),
        effective_mode="blocked",
        public_mode="blocked",
        executor_profile="blocked",
        approval=ApprovalExitSignal(blocked=True),
        primary_path_candidate="approval_gate",
        answer_type="approval_blocked",
        pipeline_ok=False,
    )
    return apply_turn_exit_to_chat_turn(
        build_chat_turn_result(
            answer=build_approval_blocked_answer(result),
            session_id=session_id,
            request_id=request_id,
            answer_type="approval_blocked",
            pipeline_ok=False,
            extra=extra,
            elapsed_ms=elapsed_ms,
        ),
        facts=facts,
        ingress=ingress,
    )


def build_commit_executed_turn_result(
    *,
    message: str,
    session_id: str | None,
    request_id: str | None,
    elapsed_ms: int,
    ingress: Any | None,
    commit_result: Any,
    extra_base: dict[str, Any] | None = None,
) -> dict[str, Any]:
    extra = build_common_exit_extra(
        extra_base={
            "lane": "approval_gate",
            EXIT_SIGNAL_PRIMARY_PATH: "approval_gate",
            **(extra_base or {}),
        },
        ingress=ingress,
        mode="fast",
        executor_profile="fast",
        progress_stage="commit_executed",
        elapsed_ms=elapsed_ms,
    )
    extra.update(
        {
            "approval_gate.required": True,
            "approval_gate.kind": "pending_commit",
            "approval_gate.reason": "execute_commit",
            "approval_gate.blocked": False,
            "approval_gate.executed": True,
            "commit_success": bool(getattr(commit_result, "success", False)),
            "commit_pending_id": getattr(commit_result, "pending_id", "") or "",
            "commit_source_id": getattr(commit_result, "source_id", "") or "",
            "commit_chunk_count": int(getattr(commit_result, "chunk_count", 0) or 0),
        }
    )
    from application.chat.material_lifecycle import (
        committed_material_from_result,
        trace_fields_for_state,
    )

    committed = committed_material_from_result(commit_result, session_id=session_id or "")
    commit_trace = trace_fields_for_state(
        "committed" if committed.success else "failed",
        source_count=committed.chunk_count,
    )
    extra.update(material_trace_for_extra(executor_profile="fast", approval_kind="pending_commit", pending_count=0))
    extra.update(commit_trace)
    commit_ok = bool(getattr(commit_result, "success", False))
    set_mode_signal(extra, "fast")
    set_material_sufficiency_signal(extra, "sufficient" if commit_ok else "insufficient")
    title = str(getattr(commit_result, "title", "") or getattr(commit_result, "source_id", "") or "资料")
    chunks = int(getattr(commit_result, "chunk_count", 0) or 0)
    if commit_ok:
        answer = f"已成功保存到知识库：{title}（{chunks} 个片段）。"
        pipeline_ok = True
    else:
        code = str(getattr(commit_result, "error_code", "") or "commit_failed")
        answer = f"保存失败（{code}）。请确认 pending 资料仍有效后重试。"
        pipeline_ok = False
    facts = TurnFacts(
        router_lane=str(getattr(ingress, "lane", "general") or "general"),
        effective_mode="fast",
        public_mode="fast",
        executor_profile="fast",
        approval=ApprovalExitSignal(commit_executed=True, commit_success=commit_ok),
        primary_path_candidate="approval_gate",
        answer_type="commit_executed",
        pipeline_ok=pipeline_ok,
    )
    return apply_turn_exit_to_chat_turn(
        build_chat_turn_result(
            answer=answer,
            session_id=session_id,
            request_id=request_id,
            answer_type="commit_executed",
            pipeline_ok=pipeline_ok,
            extra=extra,
            elapsed_ms=elapsed_ms,
        ),
        facts=facts,
        ingress=ingress,
    )


def try_execute_commit_turn(
    *,
    message: str,
    session_id: str | None,
    request_id: str | None,
    elapsed_ms: int,
    ingress: Any | None,
    extra_base: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """When user confirms save and pending exists, execute commit and return turn result."""
    if not approval_gate_active() or not is_commit_intent(message) or not session_id:
        return None
    from services.capabilities.knowledge import pending_ingestion_service

    pending_items = pending_ingestion_service.list_pending(session_id, only_committable=True)
    if not pending_items:
        return None
    commit_result = pending_ingestion_service.commit_most_recent_pending(session_id)
    return build_commit_executed_turn_result(
        message=message,
        session_id=session_id,
        request_id=request_id,
        elapsed_ms=elapsed_ms,
        ingress=ingress,
        commit_result=commit_result,
        extra_base=extra_base,
    )
