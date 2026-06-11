"""Complex pipeline — session writeback, extra assembly, exit gate (Round 7)."""

from __future__ import annotations

import time
from dataclasses import replace
from typing import Any

from domain.session_types import PrevVideoRef
from application.chat.budget_clock import format_ms as _format_ms
from application.chat.complex_pending_mapping import complex_pending_kind_active
from application.chat.executors.complex_executor import (
    build_complex_turn_result as _build_complex_turn_result,
    finalize_complex_exit_extra as _finalize_complex_exit_extra,
)
from application.chat.exit_signals import primary_path_signal_from_extra
from application.chat.path_labels import resolve_complex_primary_path
from application.chat.pending_kind import PendingKind
from application.chat.pipeline.fast_stage import build_merge_turn_obs, finalize_turn_cache
from application.chat.pipeline.pipeline_state import TurnPipelineState
import application.chat.response_assembly as response_assembly
from application.chat.turn_exit_gate import apply_turn_exit_to_chat_turn
from application.chat.turn_facts import build_complex_turn_facts, quality_gate_from_extra
from schemas import ChatTurnResult


def run_complex_finalize_stage(
    state: TurnPipelineState,
    *,
    plan: Any,
    bundle: Any,
    main_dec: Any,
    answer_text: str,
    complex_delivery_extra: dict[str, Any],
    knowledge_block: Any,
    web_block: Any,
    collab_trace: list[str],
    answer_started_remaining_ms: int,
    hard_deadline_limited: bool,
) -> ChatTurnResult:
    ts = time.perf_counter()
    with state.deps.lock:
        state.hist.append((state.message.strip(), answer_text))
        _v13_video_pending = (
            bundle.pending_item is not None
            and getattr(bundle.pending_item, "source_type", "") in ("local_video", "web_video")
        )
        if bundle.v11_pending_video_text is not None and not _v13_video_pending:
            state.deps.session_pending_video[state.key] = bundle.v11_pending_video_text  # type: ignore[assignment]
        elif bundle.v11_saved_to_kb:
            state.deps.session_pending_video.pop(state.key, None)
        if bundle.v11_saved_to_kb and bundle.v11_saved_source_id:
            state.deps.session_prev_video[state.key] = PrevVideoRef(
                source_id=bundle.v11_saved_source_id,
                basename=bundle.v11_saved_title,
                path=None,
            )
    state.timing["session_update_ms"] = _format_ms((time.perf_counter() - ts) * 1000)

    from application.chat.answer_text_polish import polish_user_answer

    answer_text = polish_user_answer(answer_text)
    from config.cost_rule import COST

    if len(answer_text) > COST.max_output_chars:
        answer_text = answer_text[: COST.max_output_chars]

    ts = time.perf_counter()
    extra = response_assembly.build_extra(
        state.message,
        plan,
        bundle,
        main_dec,
        answer_text,
        state.deps,
        use_knowledge=state.use_knowledge,
        knowledge_block=knowledge_block,
        web_block=web_block,
        collab_trace=collab_trace,
        history_snapshot=state.history_snapshot,
    )
    state.timing["extra_build_ms"] = _format_ms((time.perf_counter() - ts) * 1000)
    elapsed_ms = _format_ms((time.perf_counter() - state.t0) * 1000)
    extra = _finalize_complex_exit_extra(
        base_extra=extra,
        timing=state.timing,
        ingress=state.ingress,
        effective_mode=state.effective_mode,
        elapsed_ms=elapsed_ms,
        shared_prep=state.shared_prep,
        complex_delivery_extra=complex_delivery_extra,
        arbitrator_reason=state.arbitrator_reason,
        arbitrator_trace=state.arbitrator_trace,
        answer_started_remaining_ms=answer_started_remaining_ms,
        budget_clock=state.budget_clock,
        deadline_at=state.deadline_at,
    )

    merge_turn_obs = build_merge_turn_obs(state)
    extra = merge_turn_obs(extra)
    finalize_turn_cache(state)
    facts = build_complex_turn_facts(
        bundle=bundle,
        extra=extra,
        ingress=state.ingress,
        effective_mode=state.effective_mode,
        history_snapshot=state.history_snapshot,
        session_pending_kind=state.session_pending_kind,
        hard_deadline_limited=hard_deadline_limited,
        public_mode=state.effective_mode,
        executor_profile="complex" if state.effective_mode == "complex" else state.effective_mode,
        primary_path_candidate=str(
            primary_path_signal_from_extra(extra)
            or extra.get("answer_view_path")
            or resolve_complex_primary_path(bundle)
            or "default"
        ),
        material_sufficiency=str(getattr(bundle, "material_sufficiency", "sufficient") or "sufficient"),
        quality_gate=quality_gate_from_extra(complex_delivery_extra),
        limitations=tuple(getattr(bundle, "answer_limitations", []) or ()),
    )
    if not complex_pending_kind_active():
        facts = replace(facts, pending_kind=PendingKind.NONE)
    return apply_turn_exit_to_chat_turn(
        _build_complex_turn_result(
            answer_text=answer_text,
            session_id=state.session_id,
            request_id=state.request_id,
            extra=extra,
            elapsed_ms=elapsed_ms,
        ),
        facts=facts,
        ingress=state.ingress,
        effective_mode=state.effective_mode,
        hard_deadline_limited=hard_deadline_limited,
        bundle_pending_item_present=getattr(bundle, "pending_item", None) is not None,
        user_message=state.message,
    )
