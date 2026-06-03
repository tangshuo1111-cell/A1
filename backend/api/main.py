"""
FastAPI 应用入口（协议层）。

启动（本地）：设置 `PYTHONPATH=backend` 且 cwd 为仓库根后执行
`uvicorn api.main:app --host 127.0.0.1 --port 8000`；推荐 `python scripts/run_dev.py --backend`。

路由边界（V9 R3 收口后）：
- 公开 / 默认主路由：
    * GET /health
    * POST /chat/agno  —— **唯一默认主 chat 路由**，承载 V6 三强 Agent + V7 视频链 + V8 会话记忆，
      前端 lib/api.ts: postChat 默认就连这里。
    * GET /tasks/{task_id}
    * GET /tasks/{task_id}/result
- 管理 / 内部：/ingest/*、/sessions/*、/internal/*（ADMIN_API_KEY 非空时校验 X-Admin-Key）

生产版第一轮：若设置环境变量 `API_BEARER_TOKEN`，则除 `/health`、`/docs`（含静态）、`/openapi.json`、`/redoc` 外均须 `Authorization: Bearer <token>`；未设置则行为与旧版一致（本地开发默认不启用）。

生产版第二轮：`POST /chat/agno` 为 **`async`** 路由，主链 `run_agno_chat_turn` 经 **`asyncio.to_thread`** 执行；`/chat/agno/upload` 同步解码与大模型调用同上；不改变 JSON 契约。

V9 R3 物理移除：
- POST /chat、POST /chat/async（旧 LangGraph 主链入口）
- services.chat_service / services.async_chat_service / workflow.* / 01_主链核心\\app.py CLI
- 全部已删除；不再以"兼容层"形态存在。

与 services.agno_chat_service、storage.pg_pool（PostgreSQL）协作。
"""

from __future__ import annotations

import logging
import uuid

from fastapi import FastAPI, Request
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
from core.errors import AppError, http_status_for_category
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
    status = http_status_for_category(exc.category)
    rid = getattr(request.state, "request_id", None)
    return JSONResponse(status_code=status, content=exc.to_api_body(request_id=rid))
