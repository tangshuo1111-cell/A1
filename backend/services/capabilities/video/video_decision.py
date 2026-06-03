"""Video lane decision helpers — path signals and prepare/fetch gating."""

from __future__ import annotations

from typing import Any

from services.capabilities.video.path_signals import extract_mp4_path_from_message
from video.url_fetch import extract_video_url


def shibie_video_yitu(*, message: str) -> dict[str, Any]:
    mp4_path = extract_mp4_path_from_message(message)
    if mp4_path:
        return {"has_video": True, "mp4_path": mp4_path, "yitu_label": "video_yitu"}
    return {"has_video": False, "mp4_path": None, "yitu_label": "no_video_yitu"}


def pan_jubu_celue_video(*, video_yitu: dict[str, Any]) -> str:
    if not video_yitu.get("has_video"):
        return "skip_no_video_yitu"
    path = (video_yitu.get("mp4_path") or "").strip()
    if not path or len(path) > 1024:
        return "skip_path_unsafe"
    return "call_video_to_text"


def shibie_video_url_yitu(*, message: str) -> dict[str, Any]:
    url = extract_video_url(message)
    if url:
        return {"has_video_url": True, "video_url": url, "yitu_label": "video_url_yitu"}
    return {"has_video_url": False, "video_url": None, "yitu_label": "no_video_url_yitu"}


def video_url_yitu_from_plan_or_message(
    *,
    plan: Any,
    message: str,
) -> tuple[dict[str, Any], str]:
    url = (getattr(plan, "video_url", None) or "").strip()
    if url:
        return (
            {"has_video_url": True, "video_url": url, "yitu_label": "video_url_yitu"},
            "main",
        )
    return shibie_video_url_yitu(message=message), "message_fallback"


def pan_jubu_celue_video_url(*, video_url_yitu: dict[str, Any]) -> str:
    if not video_url_yitu.get("has_video_url"):
        return "skip_no_video_url_yitu"
    if not (video_url_yitu.get("video_url") or "").strip():
        return "skip_no_video_url_yitu"
    return "call_url_fetch_video"


def resolve_mcp_video_decision(
    *,
    message: str,
    plan: Any,
) -> tuple[dict[str, Any], str]:
    video_yitu = shibie_video_yitu(message=message)
    decision = pan_jubu_celue_video(video_yitu=video_yitu)
    v13_prepare = getattr(plan, "v13_prepare_intent", None)
    if v13_prepare is not None and getattr(v13_prepare, "source_type", "") == "local_video":
        decision = "skip_v16_local_video"
    return video_yitu, decision
