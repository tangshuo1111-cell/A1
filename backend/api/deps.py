"""
FastAPI 依赖（协议层）：管理类路由的简单保护。

当环境变量 ADMIN_API_KEY 非空时，要求请求头 X-Admin-Key 一致；为空则不做校验（本地默认）。
与公开路由 /chat、/health 分离；ingest / tasks / sessions 使用 Depends 挂载。
"""

from __future__ import annotations

from fastapi import Header

from config.settings import settings


def verify_admin_optional(
    x_admin_key: str | None = Header(None, alias="X-Admin-Key"),
) -> None:
    exp = settings.admin_api_key
    if not exp:
        return
    if (x_admin_key or "").strip() != exp:
        from core.errors import AppError, ErrorCategory
        raise AppError(
            code="ADMIN_KEY_REQUIRED",
            message="admin key required",
            category=ErrorCategory.AUTH,
        )
