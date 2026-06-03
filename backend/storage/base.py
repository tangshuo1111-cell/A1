"""存储抽象（第三轮 B-013）：Protocol 与现有 SQLite 实现方法签名对齐，供后续 PG 后端挂接。"""

from __future__ import annotations

from typing import Any, Protocol

from rag.schema import RetrievedChunk


class ConversationStoragePort(Protocol):
    def append_turn(
        self,
        *,
        task_id: str,
        session_id: str | None,
        user_query: str,
        answer: str,
        task_status: str = "done",
        answer_type: str = "",
        has_insufficient_info_notice: bool = False,
        channels_used: list[str] | None = None,
        router_source: str = "",
        user_visible_status: str = "",
    ) -> None:
        ...

    def get_turn_by_task_id(self, task_id: str) -> dict[str, str] | None:
        ...

    def load_recent_for_session(self, session_id: str, limit: int = 20) -> list[dict[str, str]]:
        ...


class KnowledgeStoragePort(Protocol):
    def ensure_ready(self) -> None:
        ...

    def touch_placeholder(self) -> None:
        ...

    def save_document_text(
        self,
        text: str,
        source_id: str,
        *,
        source_type: str = "text",
        title: str = "",
        created_at: str = "",
        extra_metadata: dict | None = None,
    ) -> int:
        ...

    def search(self, query: str, top_k: int = 5) -> list[RetrievedChunk]:
        ...


class RuntimeDbPort(Protocol):
    """运行时库连接（当前为 SQLite；PG 阶段可改为等价同步连接类型或细分接口）。"""

    def get_connection(self) -> Any:
        ...
