"""请求级成本记录器。

每个 request_id 聚合本次请求的 LLM 调用和工具调用信息。
请求结束时由中间件调用 `flush_request_cost()` 输出汇总日志。
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from core.request_context import get_request_id

logger = logging.getLogger("light_maqa.cost")

_lock = threading.Lock()
_records: dict[str, _RequestCost] = {}


@dataclass
class _LLMCall:
    model: str
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float
    ts: float = field(default_factory=time.time)


@dataclass
class _ToolCall:
    tool_name: str
    duration_ms: float
    success: bool
    ts: float = field(default_factory=time.time)


@dataclass
class _RequestCost:
    llm_calls: list[_LLMCall] = field(default_factory=list)
    tool_calls: list[_ToolCall] = field(default_factory=list)

    @property
    def total_input_tokens(self) -> int:
        return sum(c.input_tokens for c in self.llm_calls)

    @property
    def total_output_tokens(self) -> int:
        return sum(c.output_tokens for c in self.llm_calls)

    @property
    def total_estimated_cost_usd(self) -> float:
        return sum(c.estimated_cost_usd for c in self.llm_calls)

    @property
    def total_tool_calls(self) -> int:
        return len(self.tool_calls)

    def to_summary(self) -> dict[str, Any]:
        return {
            "llm_calls": len(self.llm_calls),
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "estimated_cost_usd": round(self.total_estimated_cost_usd, 6),
            "tool_calls": self.total_tool_calls,
            "tool_success": sum(1 for t in self.tool_calls if t.success),
            "models_used": list(dict.fromkeys(c.model for c in self.llm_calls)),
        }


def _get_or_create(request_id: str) -> _RequestCost:
    with _lock:
        if request_id not in _records:
            _records[request_id] = _RequestCost()
        return _records[request_id]


def record_llm_call(
    model: str,
    input_tokens: int,
    output_tokens: int,
    estimated_cost_usd: float = 0.0,
) -> None:
    """记录一次 LLM 调用（从任意线程/协程调用）。"""
    rid = get_request_id()
    if not rid:
        return
    rec = _get_or_create(rid)
    rec.llm_calls.append(_LLMCall(
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost_usd=estimated_cost_usd,
    ))


def record_tool_call(tool_name: str, duration_ms: float, success: bool) -> None:
    """记录一次工具调用。"""
    rid = get_request_id()
    if not rid:
        return
    rec = _get_or_create(rid)
    rec.tool_calls.append(_ToolCall(
        tool_name=tool_name,
        duration_ms=duration_ms,
        success=success,
    ))


def get_accumulated_cost(request_id: str | None = None) -> float:
    """返回当前 request 已累计的估算费用（USD）。用于调用前预检。"""
    rid = request_id or get_request_id()
    if not rid:
        return 0.0
    with _lock:
        rec = _records.get(rid)
    if rec is None:
        return 0.0
    return rec.total_estimated_cost_usd


def flush_request_cost(request_id: str | None = None) -> dict[str, Any] | None:
    """请求结束时调用：输出汇总日志并清理。返回汇总 dict 或 None。"""
    rid = request_id or get_request_id()
    if not rid:
        return None
    with _lock:
        rec = _records.pop(rid, None)
    if rec is None or (not rec.llm_calls and not rec.tool_calls):
        return None
    summary = rec.to_summary()
    summary["request_id"] = rid
    logger.info(
        "request_cost request_id=%s llm_calls=%d tokens_in=%d tokens_out=%d "
        "cost_usd=%.5f tool_calls=%d",
        rid,
        summary["llm_calls"],
        summary["total_input_tokens"],
        summary["total_output_tokens"],
        summary["estimated_cost_usd"],
        summary["tool_calls"],
    )
    return summary
