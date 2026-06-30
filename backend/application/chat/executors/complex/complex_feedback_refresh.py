"""Feedback refresh helpers for KB/shared-prep follow-up rounds."""

from __future__ import annotations

from dataclasses import is_dataclass, replace
from typing import Any

from application.chat.chat_contracts import coerce_middle_agent_result
from application.chat.complex_pending_mapping import apply_multisource_budget_short_circuit


def run_multisource_refresh(
    *,
    message: str,
    plan: Any,
    bundle: Any,
    deps: Any,
    feedback_gate_result: dict[str, Any],
    gather_context: Any,
    current_round: int,
    budget_clock: Any | None,
) -> Any:
    refreshed = coerce_middle_agent_result(
        deps.middle_agent.caipan(
            message,
            plan=plan,
            shared_prep=gather_context.shared_prep,
            http_use_knowledge=gather_context.use_knowledge,
            history=gather_context.history_snapshot,
            session_id=gather_context.session_id or "",
            v13_text_content=gather_context.v13_text_content,
            v13_title=gather_context.v13_title,
            v13_file_content=gather_context.v13_file_content,
            prior_bundle=bundle,
            allowed_fallback_steps=list(feedback_gate_result.get("allowed_fallback_steps") or []),
            current_round=current_round + 1,
            feedback_gate_result=feedback_gate_result,
            clock=budget_clock,
        )
    ).bundle
    if is_dataclass(refreshed) and not isinstance(refreshed, type):
        refreshed = replace(
            refreshed,
            feedback_request=getattr(bundle, "feedback_request", None),
            feedback_gate_result=feedback_gate_result,
            used_rounds=[0, 1],
            final_answer_based_on_round="round_1",
        )
    return refreshed


def maybe_refresh_from_shared_prep(
    *,
    message: str,
    plan: Any,
    bundle: Any,
    deps: Any,
    feedback_gate_result: dict[str, Any],
    gather_context: Any | None,
    budget_clock: Any | None,
) -> Any | None:
    if gather_context is None:
        return None
    snapshot = getattr(getattr(gather_context, "shared_prep", None), "snapshot", None)
    if snapshot is None or not getattr(snapshot, "chunks", ()):
        return None
    if list(getattr(bundle, "retrieved_chunks", []) or []):
        return None

    refreshed = coerce_middle_agent_result(
        deps.middle_agent.caipan(
            message,
            plan=plan,
            shared_prep=gather_context.shared_prep,
            http_use_knowledge=gather_context.use_knowledge,
            history=gather_context.history_snapshot,
            session_id=gather_context.session_id or "",
            v13_text_content=gather_context.v13_text_content,
            v13_title=gather_context.v13_title,
            v13_file_content=gather_context.v13_file_content,
            clock=budget_clock,
        )
    ).bundle
    if is_dataclass(refreshed) and not isinstance(refreshed, type):
        refreshed = replace(
            refreshed,
            feedback_request=getattr(bundle, "feedback_request", None),
            feedback_gate_result=feedback_gate_result,
            used_rounds=[0, 1],
            final_answer_based_on_round="round_1",
        )
    return refreshed


__all__ = [
    "apply_multisource_budget_short_circuit",
    "maybe_refresh_from_shared_prep",
    "run_multisource_refresh",
]
