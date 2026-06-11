"""检索与存储相关配置（RAG / embedding / context / 数据目录）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ._helpers import _env_bool, _env_int, _env_opt_str, _env_str, _root


@dataclass
class SearchAndStorageSettings:
    """检索、存储、上下文裁剪字段。"""

    data_dir: Path = field(
        default_factory=lambda: Path(_env_str("DATA_DIR") or str(_root() / "_local" / "data"))
    )
    # 运行态数据目录（默认 _local/data）；服务端持久化数据在 PostgreSQL（DATABASE_URL）
    # postgresql:// 必填：应用仅连接 PostgreSQL，不再使用本地 SQLite 作为默认库
    database_url: str | None = field(
        default_factory=lambda: _env_opt_str("DATABASE_URL")
    )
    # Round 7: chat session + pending persistence backend (memory | pg)
    store_backend: str = field(
        default_factory=lambda: (_env_str("STORE_BACKEND", "memory").lower() or "memory")
    )
    knowledge_db_name: str = "knowledge.sqlite"
    conversation_db_name: str = "conversation.sqlite"

    enable_rag: bool = field(default_factory=lambda: _env_bool("ENABLE_RAG", True))

    context_turn_limit: int = field(default_factory=lambda: _env_int("CONTEXT_TURNS", 6))
    context_user_max_chars: int = field(
        default_factory=lambda: _env_int("CONTEXT_USER_CHARS", 400)
    )
    context_assistant_max_chars: int = field(
        default_factory=lambda: _env_int("CONTEXT_ASSISTANT_CHARS", 600)
    )
    context_min_assistant_chars: int = field(
        default_factory=lambda: _env_int("CONTEXT_MIN_ASSISTANT_CHARS", 24)
    )
    context_fetch_multiplier: int = field(
        default_factory=lambda: _env_int("CONTEXT_FETCH_MULT", 2)
    )
    context_always_keep_last: int = field(
        default_factory=lambda: _env_int("CONTEXT_KEEP_LAST", 2)
    )

    # 兼容旧环境变量名：RAG_HYBRID 现仅表示 keyword 路径内是否启用轻量 TF-IDF 重排，
    # 不再表示“默认主路就是 hybrid 检索”。
    use_tfidf_rerank: bool = field(
        default_factory=lambda: _env_bool("RAG_HYBRID", True)
    )
    rag_fts_pool_mult: int = field(
        default_factory=lambda: _env_int("RAG_FTS_POOL_MULT", 4)
    )

    # 对业务方的统一口径：默认只有 auto 主路；keyword / semantic / hybrid 只保留为
    # 内部调试/验收策略。auto 下是否实际走到 hybrid，取决于 embedding 数据是否可用。
    retrieval_mode: str = field(
        default_factory=lambda: _env_str("RETRIEVAL_MODE", "auto").lower()
    )
    embedding_enabled: bool = field(
        default_factory=lambda: _env_bool("EMBEDDING_ENABLED", True)
    )
    embedding_model_name: str = field(
        default_factory=lambda: _env_str(
            "EMBEDDING_MODEL",
            "sentence-transformers/all-MiniLM-L6-v2",
        )
    )

    session_memory_max_chars: int = field(
        default_factory=lambda: _env_int("SESSION_MEMORY_CHARS", 600)
    )

    checkpoint_backend: str = field(
        default_factory=lambda: _env_str("CHECKPOINT_BACKEND", "sqlite").lower()
    )
    runtime_db_name: str = field(
        default_factory=lambda: _env_str("RUNTIME_DB_NAME", "runtime.sqlite")
    )
