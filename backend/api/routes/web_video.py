"""公开网页视频辅助接口（时长探针，供前端长视频 ASR 确认）。"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError

from fastapi import APIRouter, Request

from api.api_errors import raise_validation
from api.rate_limit import chat_rate_limit_string, limiter
from api.schemas_http import WebVideoMetadataRequest, WebVideoMetadataResponse
from config.settings import settings
from video.url_fetch import is_supported_video_url, probe_web_video_metadata

router = APIRouter()


@router.post("/metadata", response_model=WebVideoMetadataResponse)
@limiter.limit(chat_rate_limit_string())
def post_web_video_metadata(request: Request, body: WebVideoMetadataRequest) -> WebVideoMetadataResponse:
    """yt-dlp 仅取元数据（不下媒体）。白名单外链与 ``fetch_video_text`` 一致。"""
    _ = request
    t0 = time.perf_counter()
    u = (body.url or "").strip()
    if not is_supported_video_url(u):
        raise_validation("url_not_in_whitelist", "URL 不在支持的视频站点白名单内。")
    with ThreadPoolExecutor(max_workers=1) as pool:
        fut = pool.submit(probe_web_video_metadata, u)
        try:
            out = fut.result(timeout=float(settings.v16_video_probe_timeout_sec or 12.0))
        except FutureTimeoutError:
            raise_validation(
                "video_probe_timeout",
                "视频元数据探测超时，请稍后重试。",
                http_status=504,
            )
    latency_ms = int((time.perf_counter() - t0) * 1000)
    if isinstance(out, dict):
        payload = {"ok": True, **out, "latency_ms": out.get("latency_ms", latency_ms)}
        return WebVideoMetadataResponse.model_validate(payload)
    return WebVideoMetadataResponse(ok=True, latency_ms=latency_ms)
