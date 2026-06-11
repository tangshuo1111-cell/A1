"""Agent 层包。

V8 第 1 轮：`history_context` 模块在本包内对外暴露当前会话级前文承接对象
（`SessionHistorySnapshot` / `PrevVideoRef` / `looks_like_followup_reference`），
供三强 Agent runtime 与 service 胶水层共同消费。
"""

from domain.session_types import (
    PrevVideoRef,
    SessionHistorySnapshot,
    looks_like_followup_reference,
)

__all__ = [
    "PrevVideoRef",
    "SessionHistorySnapshot",
    "looks_like_followup_reference",
]
