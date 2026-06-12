"""API-layer helpers for raising ``AppError`` with stable codes."""

from __future__ import annotations

from core.errors import AppError, ErrorCategory


def raise_validation(
    code: str,
    message: str,
    *,
    http_status: int | None = None,
) -> None:
    raise AppError(
        code=code,
        message=message,
        category=ErrorCategory.VALIDATION,
        http_status=http_status,
    )


def raise_not_found(code: str, message: str) -> None:
    raise AppError(
        code=code,
        message=message,
        category=ErrorCategory.NOT_FOUND,
    )
