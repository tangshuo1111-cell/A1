"""Video lane fast path implementation."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from application.chat.executors.fast_lanes import fast_llm
from application.chat.exit_signals import set_pending_kind_signal
from application.chat.pending_kind import PendingKind


def run_video_fast_path(
    *,
    message: str,
    session_id: str | None,
    context_block: str | None,
    clock,
) -> tuple[str, dict[str, Any]] | None:
    from application.chat.decision_arbitrator import arbitrate_mode
    from application.ingress.lane_decision_schema import LaneDecision
    from services.capabilities.video.early_video_support import video_tool_result_to_fetch_result
    from services.capabilities.video.video_contract_runtime import (
        advice_from_tool_result,
        is_video_background_recommended,
    )
    from tools.video.extract_web_video_subtitle import _extract_web_video_subtitle

    budget_clock = clock
    match = re.search(r"https?://[^\s]+", message or "", flags=re.IGNORECASE)
    url = match.group(0) if match else ""
    if not url:
        return None
    result = _extract_web_video_subtitle(url, session_id=session_id or "")
    fetch = video_tool_result_to_fetch_result(url=url, result=result)
    metadata = dict(getattr(result, "metadata", {}) or {})
    capabilities_called = ["capability.video.subtitle_probe"]
    if fetch.text_source == "asr":
        capabilities_called.append("capability.video.short_sync_asr")
    if fetch.success and (fetch.text or "").strip():
        answer_text = fast_llm.summarize_fast_material(
            lane="video", message=message, material=fetch.text, context_block=context_block
        )
        return answer_text, {
            "fast_path": "video_fast",
            "lane": "video",
            "mode": "fast",
            "v16_video_source_type": "web_video",
            "v11_middle_video_url_asr_model": str(metadata.get("model") or ""),
            "capabilities_called": capabilities_called,
            "fast_exit_reason": "video_probe_answer",
        }
    if is_video_background_recommended(result):
        host = (urlparse(url).netloc or url).strip()
        task_id = str(getattr(result, "task_id", "") or metadata.get("background_task_id") or "")
        extra: dict[str, Any] = {
            "fast_path": "video_fast_background_hint",
            "lane": "video",
            "mode": "fast",
            "v16_video_source_type": "web_video",
            "task_id": task_id,
            "capabilities_called": ["capability.video.duration_probe"],
            "fast_exit_reason": "video_background_queued",
        }
        advice = advice_from_tool_result(result)
        ingress = LaneDecision(
            lane="video",
            mode="fast",
            router_source="rule",
            router_confidence=0.9,
            router_decision_ms=0,
        )
        decided_mode, decided_reason = arbitrate_mode(
            session_pending=PendingKind.NONE,
            ingress=ingress,
            main_plan=None,
            capability_advice=advice,
            clock=budget_clock,
        )
        extra["arbitrator.decided_mode"] = decided_mode
        extra["arbitrator.decided_reason"] = decided_reason
        set_pending_kind_signal(extra, PendingKind.FAST_PENDING.value)
        if advice is not None:
            extra["capability_advice"] = advice
        if decided_mode == "async":
            extra["fast_exit_reason"] = "video_fast_pending"
        elif decided_mode == "complex":
            return None
        answer = (
            f"这个视频已进入后台处理队列，我先给你首答：当前已识别为长视频或需重处理，完成后可继续查看结果。来源：{host}。"
        )
        return answer, extra
    return None
