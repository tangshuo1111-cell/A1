"""Pipeline stage 2 — ingress, approval, arbitration, shared prep."""

from __future__ import annotations

import application.chat.shared_material_prep as shared_material_prep
import application.ingress as ingress_mod
from application.chat.decision_arbitrator import resolve_session_pending_kind
from application.chat.domain.decision import TurnDecision
from application.chat.domain.events import ingress_classified_event
from application.chat.domain.reason_codes import canonical_code
from application.chat.domain.runtime_state import TurnRuntimeState
from application.chat.pipeline.pipeline_state import TurnPipelineState
from application.chat.pipeline.turn_helpers import (
    arbitrate_turn_mode,
    maybe_return_approval_or_commit,
)
from application.chat.turn_cache import current_turn_cache, reset_turn_cache
from application.chat.turn_state_machine import TurnStateBundle, apply_event
from config.feature_flags import shared_retrieval_active
from schemas import ChatTurnResult


def run_ingress_stage(state: TurnPipelineState) -> ChatTurnResult | None:
    state.ingress = ingress_mod.resolve_lane_decision(
        message=state.message,
        session_id=state.session_id,
        request_id=state.request_id,
        use_knowledge=state.use_knowledge,
        v13_file_content=state.v13_file_content,
        v13_text_content=state.v13_text_content,
        main_agent=state.deps.main_agent,
        context_snippet=state.context_block or "",
        clock=state.budget_clock,
    )
    turn_cache = current_turn_cache()
    if turn_cache is not None:
        turn_cache.set_lane(state.ingress.lane)
    state.timing["router_decision_ms"] = state.ingress.router_decision_ms

    state.turn_state = TurnStateBundle(TurnRuntimeState(), TurnDecision())
    ingress_code = canonical_code("ingress_mode", lane=state.ingress.lane, ingress_mode=state.ingress.mode)
    state.turn_state.runtime, state.turn_state.decision = apply_event(
        state.turn_state.runtime,
        state.turn_state.decision,
        ingress_classified_event(
            lane=state.ingress.lane,
            mode=state.ingress.mode,
            reason_codes=(ingress_code,),
        ),
    )

    early_turn = maybe_return_approval_or_commit(
        message=state.message,
        session_id=state.session_id,
        request_id=state.request_id,
        confirm_long_web_video_asr=state.confirm_long_web_video_asr,
        use_knowledge=state.use_knowledge,
        v13_file_content=state.v13_file_content,
        v13_text_content=state.v13_text_content,
        ingress=state.ingress,
        timing=state.timing,
        t0=state.t0,
    )
    if early_turn is not None:
        if state.turn_cache_token is not None:
            reset_turn_cache(state.turn_cache_token)
        from application.chat.pipeline.turn_helpers import with_turn_exit_gate

        return with_turn_exit_gate(
            early_turn,
            ingress=state.ingress,
            user_message=state.message,
            approval_hold=state.approval_hold,
            history_snapshot=state.history_snapshot,
            pending_video=state.pending_video,
            prev_video_ref=state.prev_video_ref,
            v13_text_content=state.v13_text_content,
            v13_file_content=state.v13_file_content,
            stitch_applied=state.stitch_applied,
        )

    state.effective_mode, state.arbitrator_reason, state.arbitrator_trace, state.turn_state = arbitrate_turn_mode(
        ingress=state.ingress,
        pending_video=state.pending_video,
        prev_video=state.prev_video_ref,
        budget_clock=state.budget_clock,
        turn_state=state.turn_state,
    )
    state.session_pending_kind = resolve_session_pending_kind(
        pending_video=state.pending_video,
        prev_video=state.prev_video_ref,
    )

    if shared_retrieval_active():
        state.shared_prep = shared_material_prep.run_shared_material_prep(
            message=state.message,
            lane=state.ingress.lane,
            use_knowledge=state.use_knowledge,
            complex_candidate=bool(getattr(state.ingress, "complex_candidate", False)),
            clock=state.budget_clock,
        )
    return None
