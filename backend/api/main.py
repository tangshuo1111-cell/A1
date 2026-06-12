"""
FastAPI 应用入口（协议层）。

启动（本地）：设置 `PYTHONPATH=backend` 且 cwd 为仓库根后执行
`uvicorn api.main:app --host 127.0.0.1 --port 8000`；推荐 `python scripts/run_dev.py --backend`。

路由边界：
- 公开 / 默认主路由：
    * GET /health
    * POST /chat/agno  —— **唯一默认主 chat 路由**，承载三强 Agent 协作 + 视频链 + 会话记忆，
      前端 lib/api.ts: postChat 默认就连这里。
    * GET /tasks/{task_id}
    * GET /tasks/{task_id}/result
- 管理 / 内部：/ingest/*、/sessions/*、/internal/*（ADMIN_API_KEY 非空时校验 X-Admin-Key）

鉴权：若设置环境变量 `API_BEARER_TOKEN`，则除 `/health`、`/docs`（含静态）、`/openapi.json`、`/redoc`
外均须 `Authorization: Bearer <token>`；未设置则默认不启用（本地开发）。

并发：`POST /chat/agno` 为 **`async`** 路由，主链 `run_agno_chat_turn` 经 **`asyncio.to_thread`** 执行；
`/chat/agno/upload` 的同步解码与大模型调用同上；不改变 JSON 契约。

与 services.agno_chat_service、storage.pg_pool（PostgreSQL）协作。
"""

from __future__ import annotations

import logging
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from api.auth import BearerAuthMiddleware
from api.lifespan import app_lifespan
from api.rate_limit import limiter
from api.routes import (
    chat_agno,
    health,
    ingest,
    internal_observability,
    sessions,
    tasks,
    video_cookies,
    web_video,
)
from config.settings import settings
from core.cost_recorder import flush_request_cost
from core.errors import AppError, ErrorCategory, http_status_for_error
from core.request_context import set_request_id, set_session_id
from observability import MetricsTimer, metrics_incr, metrics_record_request

logger = logging.getLogger("light_maqa")


def _rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    _ = request
    _ = exc
    metrics_incr("http_rate_limited_total")
    return JSONResponse(
        status_code=429,
        content={
            "ok": False,
            "error": {"code": "RATE_LIMIT", "message": "请求过于频繁，请稍后再试"},
        },
    )


app = FastAPI(title="LightMultiAgentQA", version="0.7.0", lifespan=app_lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


app.add_middleware(SlowAPIMiddleware)
app.add_middleware(BearerAuthMiddleware)

_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
if _origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(health.router, tags=["public"])
app.include_router(chat_agno.router, prefix="/chat", tags=["public-default"])
app.include_router(tasks.router, prefix="/tasks", tags=["public-default"])
app.include_router(web_video.router, prefix="/video", tags=["public-default"])
app.include_router(ingest.router, prefix="/ingest", tags=["admin"])
app.include_router(sessions.router, prefix="/sessions", tags=["admin"])
app.include_router(video_cookies.router, prefix="/config", tags=["admin"])
app.include_router(
    internal_observability.router,
    prefix="/internal",
    tags=["internal"],
)


@app.middleware("http")
async def request_logging_and_metrics(request: Request, call_next):
    rid = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.request_id = rid
    set_request_id(rid)
    set_session_id(request.headers.get("X-Session-ID", ""))
    timer = MetricsTimer()
    logger.info(
        "api request method=%s path=%s request_id=%s",
        request.method,
        request.url.path,
        rid,
    )
    if request.method == "POST" and request.url.path.startswith("/chat"):
        cl = request.headers.get("content-length")
        if cl:
            try:
                if int(cl) > settings.max_chat_body_bytes:
                    return JSONResponse(
                        status_code=413,
                        content={
                            "ok": False,
                            "error": {
                                "code": "PAYLOAD_TOO_LARGE",
                                "message": "请求体过大",
                            },
                        },
                    )
            except ValueError:
                pass
    response = await call_next(request)
    response.headers["X-Request-ID"] = rid
    metrics_record_request(
        request.url.path,
        response.status_code,
        timer.elapsed_ms(),
    )
    flush_request_cost(rid)
    set_request_id("")
    set_session_id("")
    return response


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    rid = getattr(request.state, "request_id", None)
    return JSONResponse(status_code=http_status_for_error(exc), content=exc.to_api_body(request_id=rid))


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Normalize legacy HTTPException detail dicts to ErrorResponse shape."""
    rid = getattr(request.state, "request_id", None)
    detail = exc.detail
    if isinstance(detail, dict) and detail.get("code"):
        body: dict[str, object] = {
            "ok": False,
            "error": {
                "code": str(detail["code"]),
                "message": str(detail.get("message") or ""),
                "category": ErrorCategory.VALIDATION.value,
                "error_layer": "api",
                "debug_stage": "api",
            },
        }
        if rid:
            body["request_id"] = rid
        return JSONResponse(status_code=exc.status_code, content=body)
    message = detail if isinstance(detail, str) else str(detail)
    body = {
        "ok": False,
        "error": {
            "code": "HTTP_ERROR",
            "message": message,
            "category": ErrorCategory.VALIDATION.value,
            "error_layer": "api",
            "debug_stage": "api",
        },
    }
    if rid:
        body["request_id"] = rid
    return JSONResponse(status_code=exc.status_code, content=body)
