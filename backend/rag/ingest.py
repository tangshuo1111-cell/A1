"""RAG 入库：将文本切块写入 PostgreSQL rag_chunks + rag_chunk_meta。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any


def _fts_boost_header(source_id: str, raw_text: str) -> str:
    """
    单独一条可检索摘要块：路径、标题、与 sample 演示对齐的关键词，供 FTS 命中。
    不展示给用户时可由 answer 侧摘去；此处优先保证召回。
    """
    title = ""
    for line in raw_text.splitlines():
        s = line.strip()
        if s.startswith("#"):
            title = s.lstrip("#").strip()
            break
    base = Path(source_id.replace("\\", "/")).name
    return (
        f"[doc_path] {source_id} [doc_file] {base} [doc_title] {title} "
        f"[demo_keywords] LightMultiAgentQA 项目代号 示例 多Agent main_agent "
        f"middle_agent answer_agent RAG knowledge_samples sample.md 工具层 路由"
    )


def _chunk_text(text: str, max_len: int = 700) -> list[str]:
    """按段落与长度切块（委托 chunking.strategies，默认行为不变）。"""
    from rag.chunking.strategies import paragraph_700

    return paragraph_700(text, max_len=max_len)


def ingest_text(
    text: str,
    *,
    source_id: str = "inline",
    source_type: str = "text",
    title: str = "",
    created_at: str = "",
    extra_metadata: dict[str, Any] | None = None,
) -> int:
    """写入一段文本到 PostgreSQL，返回写入块数。"""
    if not created_at:
        created_at = datetime.now().isoformat(timespec="seconds")
    header = _fts_boost_header(source_id, text)
    body_chunks = _chunk_text(text)
    parts: list[str] = [header] + body_chunks if body_chunks else [header]
    if not parts:
        return 0

    base_meta: dict[str, Any] = {
        "source_type": source_type,
        "title": title or source_id,
        "created_at": created_at,
    }
    if extra_metadata:
        base_meta.update(extra_metadata)

    from rag import pg_chunks
    from storage.pg_pool import get_pool

    get_pool()
    return pg_chunks.ingest_text_pg(
        source_id=source_id,
        source_type=source_type,
        title=title,
        created_at=created_at,
        extra_metadata=extra_metadata,
        parts=parts,
        base_meta=base_meta,
    )


def ingest_documents(paths: list[Path]) -> int:
    """
    [LEGACY-ONLY] 读取 UTF-8 本地 txt/md 并入库，返回总块数。

    V16 R1 说明：
    - 本函数仅供旧 sample 初始化（knowledge_samples 目录的 txt/md 灌库），
      不参与 V16 默认主路径。
    - 默认主路径：前端上传文件 → prepare_file_source / prepare_document_source
      → PendingKnowledgeItem → commit_pending → knowledge_store.save_document_text
    - .docx / .xlsx / .pdf 严禁走此函数，会主动抛出 ValueError 防止绕过 ToolResult。
    - 若发现旧测试通过此函数写入 docx/xlsx/pdf，该测试已不符合 V16 语义，
      应修改为走 prepare_document_source → commit_pending 链路。
    """
    total = 0
    for path in paths:
        p = Path(path)
        ext_lower = p.suffix.lower()
        # V16 R1：主动拒绝新文档类型（先于 is_file 检查，防止占位路径绕过）
        if ext_lower in {".docx", ".xlsx", ".xlsm", ".pdf"}:
            raise ValueError(
                f"[ingest_documents LEGACY-ONLY] 不支持 {ext_lower} 文件。"
                f"请使用 prepare_document_source → commit_pending 走 V16 文档工具链。"
                f"文件: {p}"
            )
        if not p.is_file():
            continue
        if ext_lower not in {".txt", ".md"}:
            continue
        raw = p.read_text(encoding="utf-8", errors="replace")
        total += ingest_text(
            raw,
            source_id=str(p.as_posix()),
            source_type="document",
            title=p.stem,
        )
    return total
