"""
V13 R1：统一 pending store（内存级，session-scoped）。

设计：
- 所有来源（text / text_file / web_url / local_video / web_video）的 PendingKnowledgeItem
  都存入同一 store
- 按 session_id 隔离；每个 session 独立 list
- 支持下一轮「保存到知识库」时找回最近 pending
- 不持久化（仅内存态）

持久化评估结论（V13 收工轮，方案 B）：
- 本版本不做 SQLite 持久化
- 理由：
  1. pending 生命周期与 session 生命周期绑定；服务重启后 session 本身也失效，
     持久化带来的实际价值有限
  2. PendingKnowledgeItem 含 mutable 字段（mark_committed 原地修改），
     序列化/反序列化需要额外同步保证
  3. 改动量约百行，会引入新的 I/O 路径和测试复杂度，不适合收工轮
- 当前风险：进程重启会丢失所有 pending 中但未 commit 的 item
- 默认行为：重启后 pending 清空，用户需重新 prepare
- 后续版本（V14+）处理方案：在 PendingStore 加 `_db_path` 参数，
  用 sqlite3 WAL 模式存储 pending（add/mark_committed/discard 同步写盘）

API：
- add(item)           → 加入 pending
- get(pending_id)     → 按 ID 取
- list_for_session(session_id) → 当前 session 所有 pending
- get_recent(session_id)       → 当前 session 最近一个 pending
- mark_committed(pending_id, source_id, chunk_count) → 标记已入库
- discard(pending_id)          → 标记已丢弃
- discard_session(session_id)  → 清除整个 session（测试用）
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

from rag.pending_schema import (
    PENDING_KIND_COMMITTED,
    STATUS_COMMITTED,
    STATUS_DISCARDED,
    PendingKnowledgeItem,
)


class PendingStore:
    """内存级 pending 存储，线程安全（使用 threading.Lock）。

    每个 PendingStore 实例是独立的；全局单例由模块级 _DEFAULT_STORE 提供。
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # { session_id: list[PendingKnowledgeItem] }（按添加顺序排列）
        self._data: dict[str, list[PendingKnowledgeItem]] = {}

    def add(self, item: PendingKnowledgeItem) -> None:
        """加入 pending，按 session_id 存储。"""
        sid = item.session_id or "__default__"
        with self._lock:
            if sid not in self._data:
                self._data[sid] = []
            self._data[sid].append(item)

    def get(self, pending_id: str) -> PendingKnowledgeItem | None:
        """按 pending_id 查找（全局搜索）。"""
        with self._lock:
            for items in self._data.values():
                for item in items:
                    if item.pending_id == pending_id:
                        return item
        return None

    def list_for_session(
        self,
        session_id: str,
        *,
        only_committable: bool = False,
    ) -> list[PendingKnowledgeItem]:
        """列出 session 的全部 pending（默认包含所有状态）。"""
        sid = session_id or "__default__"
        with self._lock:
            items = list(self._data.get(sid, []))
        if only_committable:
            items = [i for i in items if i.is_committable]
        return items

    def get_recent(
        self,
        session_id: str,
        *,
        only_committable: bool = True,
    ) -> PendingKnowledgeItem | None:
        """返回 session 中最近一个 pending（优先可提交的）。"""
        items = self.list_for_session(session_id, only_committable=only_committable)
        if not items:
            return None
        return items[-1]

    def mark_committed(
        self,
        pending_id: str,
        *,
        committed_source_id: str,
        chunk_count: int,
    ) -> bool:
        """把指定 pending 标记为 committed，填充 source_id / chunk_count。返回是否找到。"""
        with self._lock:
            for items in self._data.values():
                for item in items:
                    if item.pending_id == pending_id:
                        item.commit_status = STATUS_COMMITTED
                        item.committed_source_id = committed_source_id
                        item.committed_chunk_count = chunk_count
                        item.pending_kind = PENDING_KIND_COMMITTED
                        return True
        return False

    def discard(self, pending_id: str) -> bool:
        """把指定 pending 标记为 discarded。返回是否找到。"""
        with self._lock:
            for items in self._data.values():
                for item in items:
                    if item.pending_id == pending_id:
                        item.commit_status = STATUS_DISCARDED
                        return True
        return False

    def discard_session(self, session_id: str) -> None:
        """清除整个 session 的 pending 数据（主要供测试使用）。"""
        sid = session_id or "__default__"
        with self._lock:
            self._data.pop(sid, None)

    def count_committable(self, session_id: str) -> int:
        return len(self.list_for_session(session_id, only_committable=True))


# ── 全局默认单例 ──────────────────────────────────────────────────────────
_DEFAULT_STORE = PendingStore()


def get_default_store() -> PendingStore:
    """返回全局默认 pending store 单例。"""
    return _DEFAULT_STORE


def reset_for_tests() -> None:
    """测试用：清空全局 pending store。"""
    with _DEFAULT_STORE._lock:
        _DEFAULT_STORE._data.clear()
