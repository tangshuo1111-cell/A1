"""
V2：最小样例知识检索接线（挂在 V1 Agno 主链上，不经旧 workflow）。

只复用 storage.knowledge_store → 底层 rag.ingest / retriever 链路；
不新建对外路由、不封装第二套知识库。

V12 变更：
- fetch_knowledge_chunks() 新入口，返回 list[RetrievedChunk]（V12 统一出口）
- fetch_knowledge_block() / fetch_knowledge_block_by_source_id() 保留，
  内部改用统一出口转换，不再直接操作旧字段
"""

from __future__ import annotations

import logging
from pathlib import Path

from config.settings import settings
from core.errors import AppError, ErrorCategory
from rag.schema import RetrievedChunk
from storage import knowledge_store

logger = logging.getLogger("light_maqa")

# 与 ingest 使用的 source_id 对齐，便于测试清理
SAMPLE_SOURCE_ID = "knowledge_samples/sample.md"


def _sample_md_path() -> Path:
    """兼容新旧目录布局的 sample.md 路径。"""
    candidates = (
        settings.project_root / "knowledge_samples" / "sample.md",
        settings.project_root / "08_数据与样例" / "knowledge_samples" / "sample.md",
    )
    for path in candidates:
        if path.is_file():
            return path
    return candidates[0]


def ingest_default_sample_md() -> int:
    """
    将 `knowledge_samples/sample.md` 写入本地知识库。
    返回写入块数；文件不存在则报错。
    """
    path = _sample_md_path()
    if not path.is_file():
        raise AppError(
            code="SAMPLE_MD_MISSING",
            message=f"找不到样例知识文件: {path}",
            category=ErrorCategory.NOT_FOUND,
        )
    text = path.read_text(encoding="utf-8")
    n = knowledge_store.save_document_text(
        text,
        source_id=SAMPLE_SOURCE_ID,
        source_type="document",
        title="sample.md",
    )
    logger.info("agno_rag_service ingest sample.md chunks=%s", n)
    return n


# ------------------------------------------------------------------ #
#  V14 R1 主出口：返回 list[RetrievedChunk]（通过统一检索主入口）        #
# ------------------------------------------------------------------ #

def fetch_knowledge_chunks(
    query: str,
    *,
    top_k: int = 5,
    strategy: str = "auto",
    filters: dict | None = None,
) -> list[RetrievedChunk]:
    """
    V14 R1 主出口：按用户问题检索，返回 list[RetrievedChunk]。

    V14 R1 升级：
    - 新增 strategy 参数（keyword / semantic / auto），默认 auto
    - 新增 filters 参数（source_type / source_id / title）
    - 内部改用统一检索主入口 retrieve_knowledge（不再直接调 knowledge_store.search）
    - retrieve_knowledge 的 trace_info 写入 logger（Middle 从 bundle.trace 看）

    Middle Agent / trace 使用本接口拿到结构化 chunks，
    再自行决定是否要拼成 prompt context。
    """
    q = (query or "").strip()
    if not q:
        return []
    if not settings.enable_rag:
        return []
    try:
        from rag.retrieve_knowledge import retrieve_knowledge
        chunks, trace_info = retrieve_knowledge(
            q,
            top_k=top_k,
            strategy=strategy,
            filters=filters or {},
        )
        logger.debug(
            "fetch_knowledge_chunks strategy_used=%s hits=%s no_match=%s low_conf=%s",
            trace_info.get("strategy_used"),
            trace_info.get("hits"),
            trace_info.get("no_match"),
            trace_info.get("low_confidence"),
        )
        return chunks
    except Exception as e:  # noqa: BLE001
        logger.warning("agno_rag_service fetch_knowledge_chunks failed: %s", e)
        return []


def fetch_knowledge_chunks_by_source_id(
    source_id: str,
    *,
    top_k: int = 5,
    skip_boost_header: bool = True,
) -> list[RetrievedChunk]:
    """
    V12 辅助出口：按 source_id 精确拉同一 source 的入库块，返回 list[RetrievedChunk]。

    用于 V8 follow-up 场景（按结构化锚点 source_id 取已知 source 的块），
    避免退化成"自然语言 → FTS5 相关性"的二级检索。
    """
    sid = (source_id or "").strip()
    if not sid:
        return []
    if not settings.enable_rag:
        return []
    from rag.store import init_schema

    init_schema()
    rows: list[tuple[int, str, str]] = []
    try:
        from rag import pg_chunks

        rows = pg_chunks.fetch_chunks_by_source_pg(sid, max(1, top_k * 2))
    except Exception as e:  # noqa: BLE001
        logger.warning("agno_rag_service fetch_by_source_id failed: %s", e)
        return []
    if not rows:
        return []

    chunks: list[RetrievedChunk] = []
    idx = 0
    for rowid, src, content in rows:  # noqa: B007
        body = (content or "").strip()
        if not body:
            continue
        if skip_boost_header and body.startswith("[doc_path]"):
            continue
        chunk_id = f"{src}::chunk::{idx}"
        chunks.append(
            RetrievedChunk(
                source_id=src,
                chunk_id=chunk_id,
                text=body[:2000],
                metadata={"source_type": "text", "title": src, "chunk_index": idx},
                score=0.0,
                retrieval_strategy="source_id_exact",
            )
        )
        idx += 1
        if len(chunks) >= top_k:
            break
    return chunks


# ------------------------------------------------------------------ #
#  兼容接口：拼成纯文本（内部已改用统一出口）                             #
# ------------------------------------------------------------------ #

def fetch_knowledge_block_by_source_id(
    source_id: str,
    *,
    top_k: int = 5,
    skip_boost_header: bool = True,
) -> str:
    """[兼容层 - B 类保留] 按 source_id 精确拉块，拼成纯文本 knowledge_block。

    V13 收工版身份：B 类永久兼容接口（不退场）。
    - 仍被旧测试 patch（test_agno_rag 等），不会删除。
    - 默认主路径不调用：Middle 已改用 fetch_knowledge_chunks_by_source_id（V12 主出口）。
    - 不得重新引入到任何默认路径。
    """
    chunks = fetch_knowledge_chunks_by_source_id(
        source_id, top_k=top_k, skip_boost_header=skip_boost_header
    )
    if not chunks:
        return ""
    parts = [c.to_context_line() for c in chunks]
    return "\n\n---\n\n".join(parts)


def fetch_knowledge_block(query: str, *, top_k: int = 5) -> str:
    """[兼容层 - B 类保留] 按用户问题做最小检索，拼成纯文本。

    V13 收工版身份：B 类永久兼容接口（不退场）。
    - 仍被大量旧测试 patch（test_agno_rag, test_v6_*, test_v7_*, test_answer_agent 等）。
    - 默认主路径不调用：Middle 已直接调 fetch_knowledge_chunks + 自行拼文本（V12 主出口）。
    - 不得重新引入到任何默认路径。
    """
    chunks = fetch_knowledge_chunks(query, top_k=top_k)
    if not chunks:
        return ""
    parts = [c.to_context_line() for c in chunks]
    return "\n\n---\n\n".join(parts)
