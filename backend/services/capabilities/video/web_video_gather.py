"""Complex gather: concurrent web video probe + tool chain."""

from __future__ import annotations

import contextvars
import logging
import time
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass
from typing import Any

from services.capabilities.knowledge.pending_ingestion_service import prepare_video_source
from services.capabilities.knowledge.pending_service import SOURCE_TYPE_WEB_VIDEO
from services.capabilities.video.early_video_support import (
    queued_web_video_pending_item,
    run_fast_subtitle_probe,
    run_web_video_tool,
    video_tool_result_to_fetch_result,
)
from services.capabilities.video.video_contract_runtime import is_video_background_recommended
from video.url_fetch import FetchVideoResult, fetch_video_text

logger = logging.getLogger("light_maqa")


@dataclass
class EarlyWebVideoOutcome:
    early_web_video_url_normalized: str = ""
    video_url_result: FetchVideoResult | None = None
    video_url_kb_block: str | None = None
    video_url_ingest_error: str = ""
    web_video_pending_early: Any = None


def run_early_web_video_flow(
    *,
    video_url_decision: str,
    video_url_yitu: dict[str, Any],
    plan: Any,
    session_id: str,
    blocked_failures: list[dict[str, Any]],
    is_tool_allowed: Callable[[Any, str], bool],
    fetch_video_text_fn: Any | None = None,
) -> EarlyWebVideoOutcome:
    fetch_fn = fetch_video_text_fn if fetch_video_text_fn is not None else fetch_video_text
    out = EarlyWebVideoOutcome()
    if video_url_decision != "call_url_fetch_video":
        return out
    out.early_web_video_url_normalized = str(video_url_yitu.get("video_url") or "").strip()
    video_url = out.early_web_video_url_normalized
    if not is_tool_allowed(plan, "prepare_web_video"):
        blocked_failures.append({
            "tool": "prepare_web_video",
            "reason": "not_allowed_by_plan",
            "recoverable": False,
        })
        return out
    t0 = time.perf_counter()
    pool: ThreadPoolExecutor | None = None

    def _submit_with_context(executor: ThreadPoolExecutor, fn: Any) -> Any:
        ctx = contextvars.copy_context()
        return executor.submit(lambda: ctx.run(fn))

    try:
        pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="web-video-fast")
        tool_future = _submit_with_context(
            pool,
            lambda: run_web_video_tool(url=video_url, session_id=session_id),
        )
        probe_future = _submit_with_context(
            pool,
            lambda: run_fast_subtitle_probe(url=video_url, fetch_fn=fetch_fn),
        )
        done, _pending = wait({tool_future, probe_future}, return_when=FIRST_COMPLETED)
        first = next(iter(done))
        if first is probe_future:
            probe_result = probe_future.result()
            if probe_result is not None and probe_result.success and probe_result.text:
                out.video_url_result = probe_result
            else:
                tool_result = tool_future.result()
                if is_video_background_recommended(tool_result):
                    out.web_video_pending_early = queued_web_video_pending_item(
                        session_id=session_id,
                        url=video_url,
                        result=tool_result,
                    )
                out.video_url_result = video_tool_result_to_fetch_result(url=video_url, result=tool_result)
        else:
            tool_result = tool_future.result()
            if is_video_background_recommended(tool_result):
                out.web_video_pending_early = queued_web_video_pending_item(
                    session_id=session_id,
                    url=video_url,
                    result=tool_result,
                )
            tool_fetch_result = video_tool_result_to_fetch_result(url=video_url, result=tool_result)
            if tool_fetch_result.success or is_video_background_recommended(tool_result):
                out.video_url_result = tool_fetch_result
            else:
                out.video_url_result = probe_future.result()
    except Exception as exc:  # noqa: BLE001
        out.video_url_result = FetchVideoResult.failure(
            stage="metadata",
            error=f"fetch_raised:{type(exc).__name__}",
            source_url=video_url,
        )
    finally:
        if pool is not None:
            pool.shutdown(wait=False, cancel_futures=True)
    duration_ms = int((time.perf_counter() - t0) * 1000)
    from core.cost_recorder import record_tool_call

    record_tool_call(
        "video_fetch",
        duration_ms,
        success=(out.video_url_result is not None and out.video_url_result.success),
    )
    vr = out.video_url_result
    if vr is not None and vr.success and vr.text and out.web_video_pending_early is None:
        try:
            extra = getattr(vr, "extra", None) or {}
            slang = extra.get("subtitle_lang", "") if isinstance(extra, dict) else ""
            out.web_video_pending_early = prepare_video_source(
                source_type=SOURCE_TYPE_WEB_VIDEO,
                raw_source=video_url,
                video_text=vr.text,
                session_id=session_id,
                title=str(vr.title or "").strip() or video_url,
                duration_sec=float(vr.duration_sec or 0),
                text_source=str(vr.text_source or ""),
                subtitle_lang=str(slang or ""),
                asr_provider=str(vr.asr_provider or ""),
            )
            out.video_url_kb_block = "v13_pending_material"
        except Exception as prep_exc:  # noqa: BLE001
            logger.warning("v13 prepare_web_video failed: %s", prep_exc)
            out.video_url_ingest_error = (
                f"prepare_web_video_failed:{type(prep_exc).__name__}:{str(prep_exc)[:80]}"
            )
    return out
