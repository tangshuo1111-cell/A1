"""
统一文档工具结果结构（MCP-compatible Adapter 标准）。

DocumentToolResult 是所有文档工具（parse_text / parse_docx / parse_excel / parse_pdf
等）的唯一输出格式。

Middle / pending_ingestion_service 通过 tool_name / status / error_code 判断后续处理；
不直接消费散字段。

mcp_mode 固定为 "mcp_compatible_adapter"（本轮不外置 MCP Server；原因见 registry.py）。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class DocumentToolResult:
    """
    统一文档 ToolResult（所有文档 MCP-compatible Adapter 必须返回此类型）。

    必填字段：tool_name, status, source_type。
    失败时：text 为空，error_code / failure_reason 必须有值。
    成功时：text 不为空，metadata / quality 必须有值。
    """

    # ── 工具标识 ─────────────────────────────────────────────────────────
    tool_name: str                          # e.g. "parse_docx"
    tool_call_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    mcp_mode: str = "mcp_compatible_adapter"

    # ── 执行状态 ─────────────────────────────────────────────────────────
    status: str = "failed"                  # success | partial | failed
    source_type: str = ""                   # txt | md | docx | xlsx | pdf

    # ── 内容产出 ─────────────────────────────────────────────────────────
    text: str = ""                          # 清洗后正文（用于入库/检索）
    structured_data: dict[str, Any] = field(default_factory=dict)

    # ── 元数据与质量 ──────────────────────────────────────────────────────
    metadata: dict[str, Any] = field(default_factory=dict)
    quality: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    # ── 失败信息 ──────────────────────────────────────────────────────────
    error_code: str = ""
    failure_reason: str = ""
    next_action_hint: str = ""

    # ── 性能/成本 ─────────────────────────────────────────────────────────
    duration_ms: float = 0.0
    cost_used: float = 0.0
    task_id: str = ""

    # ── 追踪 ──────────────────────────────────────────────────────────────
    trace: list[str] = field(default_factory=list)

    # ── 便利属性 ──────────────────────────────────────────────────────────
    @property
    def is_success(self) -> bool:
        return self.status == "success"

    @property
    def is_committable(self) -> bool:
        """只有 success 且有 text 的结果才允许进入 pending → commit。"""
        return self.status == "success" and bool((self.text or "").strip())

    def to_trace_dict(self) -> dict[str, Any]:
        """供 trace / extra 写入的精简字典，不含完整 text。"""
        return {
            "tool_name": self.tool_name,
            "tool_call_id": self.tool_call_id,
            "status": self.status,
            "source_type": self.source_type,
            "mcp_mode": self.mcp_mode,
            "error_code": self.error_code,
            "failure_reason": self.failure_reason,
            "next_action_hint": self.next_action_hint,
            "duration_ms": self.duration_ms,
            "task_id": self.task_id,
            "text_length": len(self.text or ""),
            "quality_level": (self.quality or {}).get("quality_level", ""),
            "warnings": self.warnings[:5],
            "trace": self.trace[:10],
        }
