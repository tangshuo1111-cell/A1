"""Complex finalize — session-side writeback (no routing / exit fields)."""

from __future__ import annotations

from typing import Any

from domain.session_types import PrevVideoRef


def writeback_complex_session(state: Any, bundle: Any, answer_text: str) -> None:
    with state.deps.lock:
        state.hist.append((state.message.strip(), answer_text))
        video_pending = (
            bundle.pending_item is not None
            and getattr(bundle.pending_item, "source_type", "") in ("local_video", "web_video")
        )
        if bundle.v11_pending_video_text is not None and not video_pending:
            state.deps.session_pending_video[state.key] = bundle.v11_pending_video_text  # type: ignore[assignment]
        elif bundle.v11_saved_to_kb:
            state.deps.session_pending_video.pop(state.key, None)
        if bundle.v11_saved_to_kb and bundle.v11_saved_source_id:
            state.deps.session_prev_video[state.key] = PrevVideoRef(
                source_id=bundle.v11_saved_source_id,
                basename=bundle.v11_saved_title,
                path=None,
            )
