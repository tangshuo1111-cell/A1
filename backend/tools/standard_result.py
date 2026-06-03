"""
工具层标准结果结构（tools / 协议子层）。

统一外部检索、抓取、HTTP 的返回形状，便于 middle_agent 拼入 evidence 与 trace。
不参与业务编排；由具体工具模块构造，policy 与 LangGraph 只消费摘要字段。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExternalEvidenceRecord:
    """单条外部来源证据（可映射为 EvidencePack 中的一行文本）。"""

    source: str = "external"
    title: str = ""
    url: str = ""
    snippet: str = ""
    content: str = ""
    status: str = "ok"  # ok | error
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
