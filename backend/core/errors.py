"""
统一错误模型（协议层 / 服务层 / workflow 共用）。

分层说明：
- 用 ErrorCategory 归类，便于 API 映射 HTTP 状态码与日志字段。
- AppError 可携带 details 供 trace；勿在业务层随意抛裸 Exception。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ErrorCategory(str, Enum):  # noqa: UP042
    VALIDATION = "validation"  # 入参、schema
    AUTH = "auth"  # 认证/授权
    STORAGE = "storage"  # SQLite / 文件
    TOOL = "tool"  # Function Call
    LLM = "llm"  # 路由或外部模型
    WORKFLOW = "workflow"  # 编排层
    NOT_FOUND = "not_found"
    INTERNAL = "internal"


@dataclass
class AppError(Exception):
    """应用内统一异常：日志与 API 错误体结构一致。"""

    code: str
    message: str
    category: ErrorCategory = ErrorCategory.INTERNAL
    details: dict[str, Any] = field(default_factory=dict)
    http_status: int | None = None

    def to_log_dict(self) -> dict[str, Any]:
        return {
            "error_code": self.code,
            "error_message": self.message,
            "error_category": self.category.value,
            **self.details,
        }

    def to_api_body(self, *, request_id: str | None = None) -> dict[str, Any]:
        layer = error_layer_for_category(self.category)
        body: dict[str, Any] = {
            "ok": False,
            "error": {
                "code": self.code,
                "message": self.message,
                "category": self.category.value,
                "error_layer": layer,
                "debug_stage": "api",
            },
        }
        if request_id:
            body["request_id"] = request_id
        return body


def error_layer_for_category(cat: ErrorCategory) -> str:
    """与 pipeline_debug.error_layer 命名对齐，便于前端统一映射。"""
    if cat == ErrorCategory.VALIDATION:
        return "api"
    if cat == ErrorCategory.NOT_FOUND:
        return "api"
    if cat == ErrorCategory.STORAGE:
        return "storage"
    if cat == ErrorCategory.TOOL:
        return "tool"
    if cat == ErrorCategory.LLM:
        return "route"
    if cat == ErrorCategory.WORKFLOW:
        return "workflow"
    return "unknown"


def http_status_for_error(exc: AppError) -> int:
    if exc.http_status is not None:
        return exc.http_status
    return http_status_for_category(exc.category)


def http_status_for_category(cat: ErrorCategory) -> int:
    if cat == ErrorCategory.VALIDATION:
        return 400
    if cat == ErrorCategory.AUTH:
        return 403
    if cat == ErrorCategory.NOT_FOUND:
        return 404
    upstream = (
        ErrorCategory.STORAGE,
        ErrorCategory.TOOL,
        ErrorCategory.LLM,
        ErrorCategory.WORKFLOW,
    )
    if cat in upstream:
        return 502
    return 500
