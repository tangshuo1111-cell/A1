"""Complex path deadline short-circuit helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FeedbackGatherContext:
    use_knowledge: bool
    history_snapshot: Any
    session_id: str | None
    v13_text_content: str | None
    v13_title: str | None
    v13_file_content: str | bytes | None
    shared_prep: Any | None = None


def build_deadline_limited_answer(bundle: Any) -> tuple[str, str]:
    pending_item = getattr(bundle, "pending_item", None)
    source_type = str(getattr(pending_item, "source_type", "") or getattr(bundle, "v13_source_type", "") or "")
    if source_type in {"web_video", "local_video"} or getattr(bundle, "mcp_video_pending_id", None):
        return "视频材料仍在处理中，我先在 20 秒截止前返回主响应。你可以稍后轮询任务结果，或等后台处理完成后继续追问。", "pending"
    return "我先在 20 秒截止前返回当前结果。现有材料不足以继续扩展，建议补充来源或稍后继续。", "partial"
