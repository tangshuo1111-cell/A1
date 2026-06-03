"""知识库存储（PostgreSQL 唯一后端）。"""

from __future__ import annotations

import logging

from rag.schema import RetrievedChunk

logger = logging.getLogger("light_maqa")


def ensure_ready() -> None:
    """确认 PG 侧 rag 表已就绪。"""
    from rag.store import init_schema

    try:
        init_schema()
    except (OSError, ValueError, RuntimeError):
        logger.exception("knowledge_store.ensure_ready 失败")
        raise


def touch_placeholder() -> None:
    """兼容旧名：工作流启动时初始化知识库。"""
    ensure_ready()


def save_document_text(
    text: str,
    source_id: str,
    *,
    source_type: str = "text",
    title: str = "",
    created_at: str = "",
    extra_metadata: dict | None = None,
) -> int:
    """将整段文本切块写入知识库，返回写入块数。"""
    from rag import ingest

    return ingest.ingest_text(
        text,
        source_id=source_id,
        source_type=source_type,
        title=title,
        created_at=created_at,
        extra_metadata=extra_metadata,
    )


def search(query: str, top_k: int = 5) -> list[RetrievedChunk]:
    """知识检索默认 facade：统一请求 auto 主路。

    说明：
    - 面向业务调用方（knowledge_store.search / search_kb）的默认语义固定为 ``auto``；
    - ``keyword`` / ``semantic`` / ``hybrid`` 仅保留给显式调试/验收入口
      （例如 services.capabilities.knowledge.retrieve_service.retrieve_knowledge）；
    - ``auto`` 的真实落点仍由 ``retrieve_knowledge`` 根据 embedding 开关、向量覆盖率
      与异常回退链决定，并通过 trace_info 暴露 ``strategy_used`` / ``auto_reason``。
    """
    from config.settings import settings
    from debug_trace import trace

    try:
        if not settings.enable_rag:
            trace("knowledge_store.search skipped enable_rag=0")
            return []

        from rag.retrieve_knowledge import retrieve_knowledge

        configured_mode = (settings.retrieval_mode or "auto").strip().lower()
        strategy = "auto"
        chunks, trace_info = retrieve_knowledge(query, top_k=top_k, strategy=strategy)
        trace(
            "knowledge_store.search "
            f"strategy_requested={trace_info.get('strategy_requested', strategy)} "
            f"strategy_used={trace_info.get('strategy_used')} "
            f"auto_reason={trace_info.get('auto_reason', '')!r} "
            f"configured_mode={configured_mode} "
            f"hits={len(chunks)} no_match={trace_info.get('no_match')} "
            f"embedding={settings.embedding_enabled}"
        )
        return chunks
    except Exception as e:  # noqa: BLE001
        logger.warning("knowledge_store.search 失败 q=%r err=%s", query[:80], e)
        trace(f"knowledge_store.search ERROR {e!s}")
        return []


def count_chunks() -> int:
    """当前 rag_chunks 行数。"""
    ensure_ready()
    from rag import pg_chunks

    return pg_chunks.count_chunks_pg()


def list_stored_source_ids(limit: int = 500) -> list[str]:
    """列出知识库中已存在的 source_id（轻量去重）。"""
    ensure_ready()
    from rag import pg_chunks

    return pg_chunks.list_stored_source_ids_pg(limit)


def save_vector_placeholder(doc_id: str, vector: list[float]) -> None:
    """TODO: 向量扩展时写入。"""
    raise NotImplementedError
