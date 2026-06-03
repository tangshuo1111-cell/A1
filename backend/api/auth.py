"""API Bearer 认证（治理工程第一轮 B-001～B-002）。

规则：
- `settings.api_bearer_token` 非空：除 `PUBLIC_PATHS` 外须带 `Authorization: Bearer <token>`。
- 为空：不启用认证（本地开发默认）。
- `OPTIONS` 始终放行，避免 CORS 预检被挡。

中间件须在 `SlowAPIMiddleware` 之后挂载（见 `api/main.py`），使请求先经 SlowAPI 再进入本层外层包装栈。
"""

from __future__ import annotations

import secrets

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from config.settings import settings
from core.errors import ErrorCategory, error_layer_for_category

# 免 Bearer 的路径（显式列出 + /docs 静态资源前缀）
_PUBLIC_EXACT: frozenset[str] = frozenset(
    {
        "/health",
        "/openapi.json",
        "/redoc",
    }
)


def _is_public_path(path: str) -> bool:
    if path in _PUBLIC_EXACT:
        return True
    if path == "/docs" or path.startswith("/docs/"):  # noqa: SIM103
        return True
    return False


def _unauthorized_response(
    *, message: str, request: Request, www_authenticate: bool
) -> JSONResponse:
    rid = getattr(request.state, "request_id", None)
    if not rid:
        rid = request.headers.get("X-Request-ID")
    body: dict = {
        "ok": False,
        "error": {
            "code": "UNAUTHORIZED",
            "message": message,
            "category": ErrorCategory.AUTH.value,
            "error_layer": error_layer_for_category(ErrorCategory.AUTH),
            "debug_stage": "api",
        },
    }
    if rid:
        body["request_id"] = rid
    headers = {"WWW-Authenticate": 'Bearer realm="api"'} if www_authenticate else {}
    # 使用 401（与「缺/错凭证」语义一致；AppError 映射里 AUTH 曾为 403，此处协议层单独约定）
    return JSONResponse(status_code=401, content=body, headers=headers)


class BearerAuthMiddleware(BaseHTTPMiddleware):
    """校验 `Authorization: Bearer`，依赖 `settings.api_bearer_token`。"""

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        secret = settings.api_bearer_token
        if not secret:
            return await call_next(request)

        if request.method.upper() == "OPTIONS":
            return await call_next(request)

        path = request.url.path
        if _is_public_path(path):
            return await call_next(request)

        header = request.headers.get("authorization")
        if not header or not header.strip():
            return _unauthorized_response(
                message="缺少 Authorization Bearer 凭证",
                request=request,
                www_authenticate=True,
            )

        scheme, _, value = header.partition(" ")
        if scheme.strip().lower() != "bearer" or not value.strip():
            return _unauthorized_response(
                message="Authorization 格式须为 Bearer token",
                request=request,
                www_authenticate=True,
            )

        token = value.strip()
        if not secrets.compare_digest(secret, token):
            return _unauthorized_response(
                message="Bearer token 无效",
                request=request,
                www_authenticate=False,
            )

        return await call_next(request)
