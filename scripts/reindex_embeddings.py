"""
历史库向量重建（v1 同步脚本）。

与 `scripts/build_embeddings.py` 等价，命名对齐「reindex」运维语义。
要求：`EMBEDDING_ENABLED=1`；首次需安装 sentence-transformers。

运行（仓库根）：

```powershell
python scripts/reindex_embeddings.py
```

规模建议：
- < 1 万 chunk：直接跑
- 1–10 万：观察日志，可中断后重跑（upsert 幂等）
- > 10 万：评估异步 reindex（backlog）
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

    if not settings.embedding_enabled:
        print("EMBEDDING_ENABLED=0 — 跳过 reindex（当前为关键词检索模式）")
        return

    get_pool()
    print(f"reindex start model={settings.embedding_model_name!r}")
    n = backfill_all_chunks()
    print(f"reindex done embedded_chunks={n}")


if __name__ == "__main__":
    main()
