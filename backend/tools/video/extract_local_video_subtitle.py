from __future__ import annotations

import tools.asr  # noqa: F401
from services.capabilities.video.local_video_extract_service import run_local_video_subtitle_extract
from tools.video.registry import VideoToolSchema, register
from tools.video.tool_result import VideoToolResult


def _extract_local_video_subtitle(file_path: str, *, session_id: str = "") -> VideoToolResult:
    return run_local_video_subtitle_extract(file_path, session_id=session_id)


register(
    VideoToolSchema(
        tool_name="extract_local_video_subtitle",
        description="Extract subtitle text from local video files using sidecar/embedded subtitles or ASR.",
        input_schema={"type": "object", "required": ["file_path"], "properties": {"file_path": {"type": "string"}}},
        output_schema={"type": "object", "properties": {"status": {"type": "string"}, "text": {"type": "string"}}},
        call_fn=_extract_local_video_subtitle,
        enabled=True,
    )
)
