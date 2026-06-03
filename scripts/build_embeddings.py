"""
为 rag_chunks 批量写入 rag_embeddings（开发/运维脚本）。

首次需: pip install sentence-transformers
运行: python scripts/build_embeddings.py

层级：运维脚本；调用 rag.indexing.embedding_indexer、storage.pg_pool。
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


def main() -> None:
    from config.settings import settings
    from rag.indexing.embedding_indexer import backfill_all_chunks
    from storage.pg_pool import get_pool

    get_pool()
    n = backfill_all_chunks()
    print(f"embedded {n} chunks model={settings.embedding_model_name!r}")


if __name__ == "__main__":
    main()
