"""
HTTP / CLI 共用的请求上下文（contextvars）。

服务层与 workflow 可通过 get_request_id() 取当前链路 ID；未设置时返回空字符串。
"""

from __future__ import annotations

import contextvars
import uuid

_request_id: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")
_session_id: contextvars.ContextVar[str] = contextvars.ContextVar("session_id", default="")


def set_request_id(rid: str | None) -> None:
    _request_id.set(rid or "")


def get_request_id() -> str:
    return _request_id.get() or ""


def new_request_id() -> str:
    rid = str(uuid.uuid4())
    _request_id.set(rid)
    return rid


def set_session_id(sid: str | None) -> None:
    _session_id.set(sid or "")


def get_session_id() -> str:
    return _session_id.get() or ""
