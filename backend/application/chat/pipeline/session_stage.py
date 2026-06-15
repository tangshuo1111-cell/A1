"""Pipeline stage 1 — session snapshot and stitch."""

from __future__ import annotations

import time
from collections import deque

from application.chat.budget_clock import format_ms as _format_ms
from application.chat.history_buffer import format_context as _format_context
from application.chat.inline_document_material import promote_message_inline_document
from application.chat.history_buffer import history_key as _history_key
from application.chat.pipeline.pipeline_state import TurnPipelineState
from application.chat.turn_cache import TurnCache, bind_turn_cache, turn_cache_active
from domain.session_types import SessionHistorySnapshot
from tasks.orchestration.turn_stitcher import (
    consume_stitch_slot,
    stitch_slot_to_inline_material,
    stitch_slot_to_pending_video,
    turn_stitcher_active,
)


def run_session_stage(state: TurnPipelineState) -> None:
    ctx = state.ctx
    deps = state.deps
    state.message = ctx.user_input
    state.session_id = ctx.session_id
    state.request_id = ctx.request_id
    state.use_knowledge = ctx.flags.use_knowledge
    state.v13_file_content = ctx.upload.file_content
    state.v13_text_content = ctx.upload.text_content
    state.v13_title = ctx.upload.title
    state.confirm_long_web_video_asr = ctx.flags.confirm_long_web_video_asr
    state.key = _history_key(state.session_id)

    if turn_cache_active():
        state.turn_cache_token = bind_turn_cache(TurnCache(request_id=state.request_id))

    effective_v13_text = state.v13_text_content
    ts = time.perf_counter()
    with deps.lock:
        state.hist = deps.histories.setdefault(state.key, deque(maxlen=deps.max_history_pairs))
        state.context_block = _format_context(state.hist)
        state.prev_video_ref = deps.session_prev_video.get(state.key)
        state.pending_video = deps.session_pending_video.get(state.key)
        if state.confirm_long_web_video_asr:
            deps.session_approval_hold.pop(state.key, None)
            state.approval_hold = None
        else:
            state.approval_hold = deps.session_approval_hold.get(state.key)
        if turn_stitcher_active():
            stitch_slot = consume_stitch_slot(state.session_id)
            if stitch_slot is not None:
                if stitch_slot.lane == "video" and state.pending_video is None:
                    state.pending_video = stitch_slot_to_pending_video(stitch_slot)
                    deps.session_pending_video[state.key] = state.pending_video
                    state.stitch_applied = True
                    state.stitch_lane = stitch_slot.lane
                elif stitch_slot.lane in ("web", "document") and not (effective_v13_text or "").strip():
                    effective_v13_text = stitch_slot_to_inline_material(stitch_slot)
                    state.stitch_applied = True
                    state.stitch_lane = stitch_slot.lane
        state.history_snapshot = SessionHistorySnapshot.from_history(
            session_id=state.session_id,
            context_block=state.context_block,
            turns=len(state.hist),
            prev_video=state.prev_video_ref,
            pending_video_text=state.pending_video,
        )
    if not (effective_v13_text or "").strip():
        promoted = promote_message_inline_document(
            state.message,
            existing_v13_text=state.v13_text_content,
            existing_file_content=state.v13_file_content,
        )
        if promoted:
            effective_v13_text = promoted
            state.inline_document_promoted = True

    state.timing["session_snapshot_ms"] = _format_ms((time.perf_counter() - ts) * 1000)
    state.v13_text_content = effective_v13_text
