"""Pipeline stage 3 — async and fast profile attempts (Round 3)."""

from __future__ import annotations

import time
from typing import Any

from application.chat.budget_clock import format_ms as _format_ms
from application.chat.executors.async_executor import AsyncExecutor
from application.chat.executors.fast_executor import (
    maybe_return_general_fast as _maybe_return_general_fast,
    maybe_return_lane_fast as _maybe_return_lane_fast,
)
from application.chat.pipeline.pipeline_state import TurnPipelineState
from application.chat.pipeline.turn_helpers import with_turn_exit_gate
from application.chat.turn_cache import current_turn_cache, reset_turn_cache
from config.feature_flags import fast_lane_active, ingress_router_active
from observability import enrich_turn_extra
from schemas import ChatTurnResult


def build_merge_turn_obs(state: TurnPipelineState):
    def _merge_turn_obs(extra: dict[str, Any]) -> dict[str, Any]:
        tc = current_turn_cache()
        if tc is not None:
            stats = tc.hits()
            extra["turn_cache.hits"] = int(stats.get("hits", 0))
            extra["turn_cache.misses"] = int(stats.get("misses", 0))
            from agents.answer_agent.llm_exec import load_answer_llm_metrics

            extra.update(load_answer_llm_metrics())
        if state.stitch_applied:
            extra["turn_stitch.applied"] = True
            if state.stitch_lane:
                extra["turn_stitch.lane"] = state.stitch_lane
        kb_calls = 1 if int(extra.get("v15_retrieved_chunks_count") or 0) > 0 else 0
        if tc is not None and int(extra.get("turn_cache.hits") or 0) > 0:
            kb_calls = max(kb_calls, 1)
        return enrich_turn_extra(extra, main_plan_call_count=1, kb_retrieve_call_count=kb_calls)

    return _merge_turn_obs


def finalize_turn_cache(state: TurnPipelineState) -> None:
    if state.turn_cache_token is not None:
        reset_turn_cache(state.turn_cache_token)


def run_fast_stage(state: TurnPipelineState) -> ChatTurnResult | None:
    merge_turn_obs = build_merge_turn_obs(state)

    def _finalize_turn_cache() -> None:
        finalize_turn_cache(state)

    if state.effective_mode == "async":
        elapsed = _format_ms((time.perf_counter() - state.t0) * 1000)
        async_result = AsyncExecutor.build_turn_result(
            message=state.message,
            ingress=state.ingress,
            effective_mode=state.effective_mode,
            arbitrator_reason=state.arbitrator_reason,
            arbitrator_trace=state.arbitrator_trace,
            session_id=state.session_id,
            request_id=state.request_id,
            elapsed_ms=elapsed,
            v13_title=state.v13_title,
            merge_turn_obs=merge_turn_obs,
        )
        _finalize_turn_cache()
        return with_turn_exit_gate(
            async_result,
            ingress=state.ingress,
            effective_mode=state.effective_mode,
            user_message=state.message,
        )

    if not ingress_router_active():
        return None

    if fast_lane_active("general"):
        fast_result, state.effective_mode, state.timing = _maybe_return_general_fast(
            message=state.message,
            use_knowledge=state.use_knowledge,
            v13_file_content=state.v13_file_content,
            v13_text_content=state.v13_text_content,
            v13_title=state.v13_title,
            context_block=state.context_block,
            ingress=state.ingress,
            shared_prep=state.shared_prep,
            effective_mode=state.effective_mode,
            timing=state.timing,
            t0=state.t0,
            deps=state.deps,
            key=state.key,
            session_id=state.session_id,
            request_id=state.request_id,
            hist=state.hist,
            merge_turn_obs=merge_turn_obs,
            finalize_turn_cache=_finalize_turn_cache,
            turn_state=state.turn_state,
        )
        if fast_result is not None:
            return with_turn_exit_gate(
                fast_result,
                ingress=state.ingress,
                effective_mode=state.effective_mode,
                user_message=state.message,
            )

    fast_result, state.effective_mode, state.timing = _maybe_return_lane_fast(
        ingress=state.ingress,
        effective_mode=state.effective_mode,
        session_id=state.session_id,
        pending_video=state.pending_video,
        prev_video_ref=state.prev_video_ref,
        message=state.message,
        context_block=state.context_block,
        budget_clock=state.budget_clock,
        v13_text_content=state.v13_text_content,
        v13_file_content=state.v13_file_content,
        v13_title=state.v13_title,
        shared_prep=state.shared_prep,
        timing=state.timing,
        t0=state.t0,
        deps=state.deps,
        key=state.key,
        request_id=state.request_id,
        hist=state.hist,
        merge_turn_obs=merge_turn_obs,
        finalize_turn_cache=_finalize_turn_cache,
        turn_state=state.turn_state,
    )
    if fast_result is not None:
        return with_turn_exit_gate(
            fast_result,
            ingress=state.ingress,
            effective_mode=state.effective_mode,
            user_message=state.message,
        )
    return None
