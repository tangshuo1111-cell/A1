"""Map V17 bundle fields + session snapshot to PendingKind (§7.6.1 / S7c)."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

from application.chat.pending_kind import PendingKind
from config.feature_flags import is_enabled

_HARD_PARTIAL_INSUFFICIENCY_SIGNALS = {
    "still_empty_after_gather",
    "required_material_missing_after_round1",
    "history_anchor_missing_source_id",
}


def complex_pending_kind_active() -> bool:
    return is_enabled("ENABLE_COMPLEX_PENDING_KIND_V2")


def _safe_replace(obj: Any, **updates: Any) -> Any:
    try:
        return replace(obj, **updates)
    except TypeError:
        for key, value in updates.items():
            setattr(obj, key, value)
        return obj


def resolve_bundle_pending_kind(
    *,
    bundle: Any,
    session_pending: PendingKind = PendingKind.NONE,
) -> PendingKind:
    """Derive PendingKind from session context and Middle/Answer bundle state."""
    if session_pending != PendingKind.NONE:
        return session_pending

    v13_pending = getattr(bundle, "pending_item", None)
    if v13_pending is not None:
        commit_status = str(getattr(v13_pending, "commit_status", "") or "").strip()
        if commit_status != "committed":
            return PendingKind.MATERIAL_PENDING

    feedback_request = getattr(bundle, "feedback_request", None)
    if isinstance(feedback_request, dict) and feedback_request:
        used_rounds = list(getattr(bundle, "used_rounds", []) or [])
        if len(used_rounds) <= 1:
            return PendingKind.PROCESSING_PENDING

    critic = dict(getattr(bundle, "critic_check", {}) or {})
    if critic.get("revision_required"):
        return PendingKind.PARTIAL_PENDING

    material_sufficiency = str(getattr(bundle, "material_sufficiency", "sufficient") or "sufficient")
    if material_sufficiency == "insufficient":
        insuff_signal = str(getattr(bundle, "insufficiency_signal", "") or "").strip().lower()
        if (
            getattr(bundle, "material_still_insufficient", False)
            and insuff_signal in _HARD_PARTIAL_INSUFFICIENCY_SIGNALS
        ):
            return PendingKind.PARTIAL_PENDING

    execution_status = str(getattr(bundle, "execution_status", "ok") or "ok")
    if execution_status == "partial":
        return PendingKind.PARTIAL_PENDING

    trace = dict(getattr(bundle, "negotiation_trace", {}) or {})
    trace_kind = str(trace.get("complex_pending_kind") or trace.get("v17_partial_status") or "").strip()
    if trace_kind in {PendingKind.PARTIAL_PENDING.value, "budget_short_circuit", "budget_exhausted"}:
        return PendingKind.PARTIAL_PENDING

    if getattr(bundle, "v11_saved_to_kb", False) or str(getattr(bundle, "v13_material_status", "") or "") == "committed":
        return PendingKind.COMMITTED

    return PendingKind.NONE


def attach_complex_pending_context(
    bundle: Any,
    *,
    session_pending: PendingKind = PendingKind.NONE,
) -> Any:
    """Record resolved PendingKind on bundle for complex-path consumers (C1)."""
    if not complex_pending_kind_active():
        return bundle
    resolved = resolve_bundle_pending_kind(bundle=bundle, session_pending=session_pending)
    trace = dict(getattr(bundle, "negotiation_trace", {}) or {})
    trace["complex_pending_kind"] = resolved.value
    return _safe_replace(bundle, negotiation_trace=trace)


def apply_multisource_budget_short_circuit(bundle: Any, *, stop_reason: str) -> Any:
    """Mark partial_pending when multisource/autonomy stops under budget (C3)."""
    limitations = list(getattr(bundle, "answer_limitations", []) or [])
    if stop_reason == "budget_exhausted":
        msg = "首响预算不足，部分证据尚未补齐。"
    elif stop_reason:
        msg = f"协商在 {stop_reason} 处停止，当前为部分结论。"
    else:
        msg = "材料尚未完全齐备，当前为部分结论。"
    if msg not in limitations:
        limitations.append(msg)
    trace = dict(getattr(bundle, "negotiation_trace", {}) or {})
    trace["complex_pending_kind"] = PendingKind.PARTIAL_PENDING.value
    trace["v17_partial_status"] = stop_reason or "partial"
    return _safe_replace(
        bundle,
        execution_status="partial",
        material_sufficiency="insufficient",
        material_still_insufficient=True,
        answer_limitations=list(dict.fromkeys(limitations)),
        negotiation_trace=trace,
    )


def task_status_for_pending_kind(pending_kind: PendingKind) -> str:
    if pending_kind == PendingKind.PARTIAL_PENDING:
        return "partial"
    if pending_kind in {
        PendingKind.FAST_PENDING,
        PendingKind.PROCESSING_PENDING,
        PendingKind.MATERIAL_PENDING,
    }:
        return "pending"
    return "succeeded"


def resolve_final_task_status(
    *,
    pending_kind: PendingKind,
    hard_deadline_limited: bool = False,
    bundle_pending_item_present: bool = False,
) -> str:
    """Resolve final public task_status from unified pending + deadline facts."""
    if pending_kind != PendingKind.NONE:
        return task_status_for_pending_kind(pending_kind)
    if hard_deadline_limited and bundle_pending_item_present:
        return "pending"
    return "succeeded"
