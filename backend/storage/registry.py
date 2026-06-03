"""按配置选择存储门面（会话/知识委托 store；运行时仅使用 PostgreSQL）。"""

from __future__ import annotations

from typing import Literal

from storage.backends_delegating import DelegatedConversationBackend, DelegatedKnowledgeBackend
from storage.backends_pg import PgRuntimeStubBackend
from storage.base import ConversationStoragePort, KnowledgeStoragePort, RuntimeDbPort

StorageBackendKind = Literal["postgres"]

_delegated_conversation = DelegatedConversationBackend()
_delegated_knowledge = DelegatedKnowledgeBackend()
_pg_runtime = PgRuntimeStubBackend()


def storage_backend_kind() -> StorageBackendKind:
    """运行时仅支持 PostgreSQL（``DATABASE_URL`` 须为 ``postgresql`` 连接串）。"""
    return "postgres"


def get_conversation_storage() -> ConversationStoragePort:
    """委托 ``conversation_store``（PostgreSQL `turns` 等）。"""
    return _delegated_conversation


def get_knowledge_storage() -> KnowledgeStoragePort:
    """委托 ``knowledge_store`` / RAG（PostgreSQL）。"""
    return _delegated_knowledge


def get_runtime_backend() -> RuntimeDbPort:
    """不使用全局 SQLite runtime；任务/会话走 PG 各模块。"""
    return _pg_runtime
