from __future__ import annotations

from typing import Any

from rag.pending_schema import SOURCE_TYPE_WEB_VIDEO, PendingKnowledgeItem, SourcePayload
from video.url_fetch import FetchVideoResult


def video_tool_result_to_fetch_result(*, url: str, result: Any) -> FetchVideoResult:
    metadata = dict(getattr(result, "metadata", {}) or {})
    status = str(getattr(result, "status", "") or "")
    title = str(getattr(result, "title", "") or url)
    duration_sec = float(metadata.get("duration") or 0.0)
    if status == "success":
        transcript_source = str(getattr(result, "transcript_source", "") or metadata.get("transcript_source") or metadata.get("text_source") or "")
        provider = str(metadata.get("provider") or "")
        model = str(metadata.get("model") or "")
        text = str(getattr(result, "text", "") or "")
        if transcript_source == "asr":
            return FetchVideoResult.ok_asr(text=text, title=title, source_url=url, source_basename=title, duration_sec=duration_sec, provider=provider, model=model, extra=metadata)
        return FetchVideoResult.ok_subtitle(text=text, title=title, source_url=url, source_basename=title, duration_sec=duration_sec, extra=metadata)
    from services.capabilities.video.video_contract_runtime import is_video_background_recommended

    if is_video_background_recommended(result):
        return FetchVideoResult.failure(stage="background", error="background_queued", source_url=url, title=title, source_basename=title, duration_sec=duration_sec, extra=metadata)
    return FetchVideoResult.failure(stage=str(getattr(result, "error_code", "") or "video_tool"), error=str(getattr(result, "failure_reason", "") or getattr(result, "error_code", "") or "video_tool_failed"), source_url=url, title=title, source_basename=title, duration_sec=duration_sec, extra=metadata)


def queued_web_video_pending_item(*, session_id: str, url: str, result: Any) -> PendingKnowledgeItem:
    metadata = dict(getattr(result, "metadata", {}) or {})
    title = str(getattr(result, "title", "") or metadata.get("title") or url)
    payload = SourcePayload(
        source_type=SOURCE_TYPE_WEB_VIDEO,
        source_id=str(metadata.get("background_task_id") or metadata.get("task_id") or url),
        raw_source=url,
        title=title,
        text="",
        metadata={
            **metadata,
            "video_tool_name": "extract_web_video_subtitle",
            "task_id": str(metadata.get("background_task_id") or metadata.get("task_id") or ""),
            "sync_strategy": str(metadata.get("sync_strategy") or "background_after_probe"),
        },
    )
    return PendingKnowledgeItem.create(session_id=session_id, payload=payload, parser_name="extract_web_video_subtitle", extract_status="queued", error_code="")


def run_fast_subtitle_probe(*, url: str, fetch_fn: Any) -> FetchVideoResult:
    try:
        return fetch_fn(url, prefer_subtitles=True, allow_asr=False)
    except TypeError:
        return fetch_fn(url)


def run_web_video_tool(*, url: str, session_id: str) -> Any:
    from tools.video.extract_web_video_subtitle import _extract_web_video_subtitle

    return _extract_web_video_subtitle(url, session_id=session_id)
