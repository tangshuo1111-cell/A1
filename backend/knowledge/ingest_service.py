"""
知识入库服务：封装 rag.ingest，供 CLI / API 共用。

支持：目录 glob 扫描、单文件路径列表、原始文本块（带 source_id）。
"""

from __future__ import annotations

from pathlib import Path

from config.settings import settings
from rag import ingest


def ingest_knowledge_samples_dir() -> int:
    """默认扫描 knowledge_samples 下 md/txt。"""
    d = settings.knowledge_samples_dir()
    paths = list(d.rglob("*.md")) + list(d.rglob("*.txt"))
    return ingest.ingest_documents(paths)


def ingest_paths(paths: list[str | Path]) -> int:
    """指定路径列表（文件）。"""
    ps = [Path(p) for p in paths]
    return ingest.ingest_documents(ps)


def ingest_text(text: str, source_id: str) -> int:
    """写入单段文本。"""
    return ingest.ingest_text(text, source_id=source_id)
