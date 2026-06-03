"""存储门面实现：委托 conversation_store / knowledge_store（内部已按 ``DATABASE_URL`` 走 PG）。"""

from __future__ import annotations

from rag.schema import RetrievedChunk
from storage import conversation_store, knowledge_store


class DelegatedConversationBackend:
    """实现 ``ConversationStoragePort``：委托 ``conversation_store``（PostgreSQL）。"""

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
        conversation_store.append_turn(
            task_id=task_id,
            session_id=session_id,
            user_query=user_query,
            answer=answer,
            task_status=task_status,
            answer_type=answer_type,
            has_insufficient_info_notice=has_insufficient_info_notice,
            channels_used=channels_used,
            router_source=router_source,
            user_visible_status=user_visible_status,
        )

    def get_turn_by_task_id(self, task_id: str) -> dict[str, str] | None:
        return conversation_store.get_turn_by_task_id(task_id)

    def load_recent_for_session(self, session_id: str, limit: int = 20) -> list[dict[str, str]]:
        return conversation_store.load_recent_for_session(session_id, limit=limit)


class DelegatedKnowledgeBackend:
    """实现 ``KnowledgeStoragePort``：委托 ``knowledge_store``（PostgreSQL RAG）。"""

    def ensure_ready(self) -> None:
        knowledge_store.ensure_ready()

    def touch_placeholder(self) -> None:
        knowledge_store.touch_placeholder()

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
        return knowledge_store.save_document_text(
            text,
            source_id,
            source_type=source_type,
            title=title,
            created_at=created_at,
            extra_metadata=extra_metadata,
        )

    def search(self, query: str, top_k: int = 5) -> list[RetrievedChunk]:
        return knowledge_store.search(query, top_k=top_k)
