from __future__ import annotations

from services.capabilities.video.web_video_extract_service import run_web_video_subtitle_extract
from tools.video.errors import SUBTITLE_NOT_FOUND as _SUBTITLE_NOT_FOUND
from tools.video.registry import VideoToolSchema, register
from tools.video.tool_result import VideoToolResult

SUBTITLE_NOT_FOUND = _SUBTITLE_NOT_FOUND


def _extract_web_video_subtitle(url: str, *, session_id: str = "") -> VideoToolResult:
    return run_web_video_subtitle_extract(url, session_id=session_id)


register(
    VideoToolSchema(
        tool_name="extract_web_video_subtitle",
        description="Extract subtitle text from web video URLs using yt-dlp metadata/subtitles.",
        input_schema={"type": "object", "required": ["url"], "properties": {"url": {"type": "string"}}},
        output_schema={"type": "object", "properties": {"status": {"type": "string"}, "text": {"type": "string"}}},
        call_fn=_extract_web_video_subtitle,
        enabled=True,
    )
)
