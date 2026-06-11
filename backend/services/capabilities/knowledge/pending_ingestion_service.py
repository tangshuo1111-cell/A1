"""
V13 R1：统一资料生命周期服务（prepare / pending / commit / list / discard）。

这是 V13 R1 的核心服务层，负责：
1. prepare_*_source：把各类来源转成 PendingKnowledgeItem，存入 pending store
2. commit_pending：用户确认保存后，调 V12 knowledge_store → ingest 正式入库
3. list_pending / get_pending / discard_pending：pending 管理

架构原则：
- commit 后走 V12 knowledge_store.save_document_text → ingest_text（统一主出口）
- 不重建第二套知识库；不复活旧 retrieve_as_legacy_dicts / fetch_knowledge_block
- prepare 只解析、不入库；commit 才入库
- pending store 仅内存（V13 R2 可升级）

三态说明：
- TEMPORARY  : 资料在当前轮进入上下文，尚未 prepare（仅当轮可用）
- PENDING    : prepare 成功，等待用户确认保存
- COMMITTED  : 用户确认，commit 后进入 V12 store，可被 retrieval 命中
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rag.pending_schema import PendingKnowledgeItem
from rag.source_parsers import (
    parse_asr_source,
    parse_document_source,
    parse_file_source,
    parse_local_video_source,
    parse_ocr_document_source,
    parse_text_source,
    parse_video_source,
    parse_web_search_source,
    parse_web_url_source,
    parse_web_video_source,
)
from services.pending_store import PendingStore, get_pending_store

logger = logging.getLogger("light_maqa")


def _sync_task_taskstore_after_prepare(item: PendingKnowledgeItem) -> None:
    """V16 R4-E：prepare 成功后把 pending_id 回填 SQLite task_jobs。"""
    if item.extract_status != "ok":
        return
    tid = (item.metadata or {}).get("v16_task_id")
    if not tid:
        return
    from storage import task_job_store

    task_job_store.update_task_pending_source(str(tid), result_pending_id=item.pending_id)


def _sync_task_taskstore_after_commit(*, pending_metadata: dict[str, Any], source_id: str) -> None:
    tid = (pending_metadata or {}).get("v16_task_id")
    if not tid or not source_id:
        return
    from storage import task_job_store

    task_job_store.update_task_pending_source(str(tid), result_source_id=source_id)


# ── commit 结果 ──────────────────────────────────────────────────────────
@dataclass
class CommitResult:
    """commit_pending 的返回值，含 trace 所需信息。"""

    success: bool
    pending_id: str
    source_id: str
    chunk_count: int
    error_code: str = ""
    title: str = ""
    source_type: str = ""

    def to_trace_dict(self) -> dict[str, Any]:
        return {
            "commit_success": self.success,
            "pending_id": self.pending_id,
            "source_id": self.source_id,
            "chunk_count": self.chunk_count,
            "error_code": self.error_code,
            "title": self.title,
            "source_type": self.source_type,
        }


# ── prepare 系列 ──────────────────────────────────────────────────────────
def prepare_text_source(
    text: str,
    *,
    session_id: str,
    title: str = "",
    store: PendingStore | None = None,
) -> PendingKnowledgeItem:
    """
    直接文本 prepare。

    返回 PendingKnowledgeItem（已加入 pending store）。
    extract_status 为 "ok" 时可用于临时回答；"empty_content" 时不可用。
    """
    _store = store or get_pending_store()
    payload, parser_name, error_code = parse_text_source(
        text, session_id=session_id, title=title
    )
    extract_status = "ok" if not error_code else error_code  # noqa: SIM212
    item = PendingKnowledgeItem.create(
        session_id=session_id,
        payload=payload,
        parser_name=parser_name,
        extract_status=extract_status,
        error_code=error_code,
    )
    _store.add(item)
    logger.info(
        "v13:prepare_text session=%s pending_id=%s status=%s",
        session_id, item.pending_id, item.extract_status,
    )
    return item


def prepare_document_source(
    file_path: str | Path,
    *,
    session_id: str,
    file_content: str | bytes | None = None,
    store: PendingStore | None = None,
) -> PendingKnowledgeItem:
    """
    V16 R1：文档类文件（.docx / .xlsx / .pdf）prepare。

    调用 document tool registry → DocumentToolResult → PendingKnowledgeItem。
    失败时 extract_status=error_code，不得 commit。
    返回 PendingKnowledgeItem（已加入 pending store）。
    """
    _store = store or get_pending_store()
    payload, parser_name, error_code = parse_document_source(
        file_path, file_content=file_content
    )
    extract_status = "ok" if not error_code else error_code  # noqa: SIM212
    item = PendingKnowledgeItem.create(
        session_id=session_id,
        payload=payload,
        parser_name=parser_name,
        extract_status=extract_status,
        error_code=error_code,
    )
    _store.add(item)
    logger.info(
        "v16:prepare_document session=%s pending_id=%s file=%s status=%s",
        session_id, item.pending_id, str(file_path)[:60], item.extract_status,
    )
    return item


def prepare_file_source(
    file_path: str | Path,
    *,
    session_id: str,
    file_content: str | bytes | None = None,
    store: PendingStore | None = None,
) -> PendingKnowledgeItem:
    """
    文本型文件（.txt / .md）prepare。
    V16 R1：.docx / .xlsx / .pdf 自动分发到 prepare_document_source。

    file_content 可传入已读取的内容（来自前端上传），否则从 file_path 读取。
    返回 PendingKnowledgeItem（已加入 pending store）。
    """
    _ext = Path(file_path).suffix.lower() if file_path else ""
    if _ext in (".docx", ".xlsx", ".xlsm", ".pdf"):
        return prepare_document_source(
            file_path,
            session_id=session_id,
            file_content=file_content,
            store=store,
        )

    _store = store or get_pending_store()
    payload, parser_name, error_code = parse_file_source(
        file_path, file_content=file_content
    )
    extract_status = "ok" if not error_code else error_code  # noqa: SIM212
    item = PendingKnowledgeItem.create(
        session_id=session_id,
        payload=payload,
        parser_name=parser_name,
        extract_status=extract_status,
        error_code=error_code,
    )
    _store.add(item)
    logger.info(
        "v13:prepare_file session=%s pending_id=%s file=%s status=%s",
        session_id, item.pending_id, str(file_path)[:60], item.extract_status,
    )
    return item


def prepare_web_url_source(
    url: str,
    *,
    session_id: str,
    fetch_method: str = "static",
    cookie: str = "",
    cookie_ref: str = "",
    cookie_domain: str = "",
    task_id: str = "",
    store: PendingStore | None = None,
) -> PendingKnowledgeItem:
    """
    V16 R2 网页 URL prepare：Web ToolResult → pending。

    返回 PendingKnowledgeItem（已加入 pending store）。
    失败时 extract_status 为 error_code；失败态不得 commit。
    """
    _store = store or get_pending_store()
    payload, parser_name, error_code = parse_web_url_source(
        url,
        fetch_method=fetch_method,
        cookie=cookie,
        cookie_ref=cookie_ref,
        cookie_domain=cookie_domain,
        task_id=task_id,
    )
    extract_status = "ok" if not error_code else error_code  # noqa: SIM212
    item = PendingKnowledgeItem.create(
        session_id=session_id,
        payload=payload,
        parser_name=parser_name,
        extract_status=extract_status,
        error_code=error_code,
    )
    _store.add(item)
    _sync_task_taskstore_after_prepare(item)
    logger.info(
        "v13:prepare_web_url session=%s pending_id=%s url=%s status=%s",
        session_id, item.pending_id, url[:60], item.extract_status,
    )
    return item


def prepare_video_source(
    *,
    source_type: str,
    raw_source: str,
    video_text: str,
    session_id: str,
    title: str = "",
    duration_sec: float = 0,
    text_source: str = "",
    subtitle_lang: str = "",
    asr_provider: str = "",
    store: PendingStore | None = None,
) -> PendingKnowledgeItem:
    """视频来源（local_video / web_video）prepare。

    参数：
    - source_type  : SOURCE_TYPE_LOCAL_VIDEO 或 SOURCE_TYPE_WEB_VIDEO
    - raw_source   : 文件路径（local）或 URL（web）
    - video_text   : 已提取的视频文本（字幕/ASR），由 Middle Agent 提取后传入
    - title        : 视频标题（可选）
    - duration_sec : 视频时长（秒，可选）
    - text_source  : "subtitle" / "asr" / ""
    - subtitle_lang: 字幕语言（可选）
    - asr_provider : ASR 服务商（可选）

    调用方（Middle Agent）负责提取视频文本；本函数只负责 payload 标准化和 pending 存储。
    返回 PendingKnowledgeItem（已加入 pending store）。
    """
    _store = store or get_pending_store()
    payload, parser_name, error_code = parse_video_source(
        source_type=source_type,
        raw_source=raw_source,
        video_text=video_text,
        title=title,
        duration_sec=duration_sec,
        text_source=text_source,
        subtitle_lang=subtitle_lang,
        asr_provider=asr_provider,
    )
    extract_status = "ok" if not error_code else error_code  # noqa: SIM212
    item = PendingKnowledgeItem.create(
        session_id=session_id,
        payload=payload,
        parser_name=parser_name,
        extract_status=extract_status,
        error_code=error_code,
    )
    _store.add(item)
    logger.info(
        "v13:prepare_video session=%s pending_id=%s source_type=%s raw=%s status=%s",
        session_id, item.pending_id, source_type, raw_source[:60], item.extract_status,
    )
    return item


def prepare_local_video_source(
    file_path: str,
    *,
    session_id: str,
    store: PendingStore | None = None,
) -> PendingKnowledgeItem:
    _store = store or get_pending_store()
    payload, parser_name, error_code = parse_local_video_source(file_path, session_id=session_id)
    extract_status = "ok" if not error_code else error_code  # noqa: SIM212
    item = PendingKnowledgeItem.create(
        session_id=session_id,
        payload=payload,
        parser_name=parser_name,
        extract_status=extract_status,
        error_code=error_code,
    )
    _store.add(item)
    logger.info("v16:prepare_local_video session=%s pending_id=%s status=%s", session_id, item.pending_id, item.extract_status)
    return item


def prepare_web_video_source(
    url: str,
    *,
    session_id: str,
    store: PendingStore | None = None,
) -> PendingKnowledgeItem:
    _store = store or get_pending_store()
    payload, parser_name, error_code = parse_web_video_source(url, session_id=session_id)
    extract_status = "ok" if not error_code else error_code  # noqa: SIM212
    item = PendingKnowledgeItem.create(
        session_id=session_id,
        payload=payload,
        parser_name=parser_name,
        extract_status=extract_status,
        error_code=error_code,
    )
    _store.add(item)
    _sync_task_taskstore_after_prepare(item)
    logger.info("v16:prepare_web_video session=%s pending_id=%s status=%s", session_id, item.pending_id, item.extract_status)
    return item


def prepare_ocr_source(
    file_path: str,
    *,
    session_id: str,
    estimated_cost: float = 0.0,
    store: PendingStore | None = None,
) -> PendingKnowledgeItem:
    _store = store or get_pending_store()
    payload, parser_name, error_code = parse_ocr_document_source(file_path, estimated_cost=estimated_cost, session_id=session_id)
    extract_status = "ok" if not error_code else error_code  # noqa: SIM212
    item = PendingKnowledgeItem.create(
        session_id=session_id,
        payload=payload,
        parser_name=parser_name,
        extract_status=extract_status,
        error_code=error_code,
    )
    _store.add(item)
    _sync_task_taskstore_after_prepare(item)
    return item


def prepare_asr_source(
    file_path: str,
    *,
    session_id: str,
    duration_sec: float = 0.0,
    estimated_cost: float = 0.0,
    store: PendingStore | None = None,
) -> PendingKnowledgeItem:
    _store = store or get_pending_store()
    payload, parser_name, error_code = parse_asr_source(
        file_path,
        duration_sec=duration_sec,
        estimated_cost=estimated_cost,
        session_id=session_id,
    )
    extract_status = "ok" if not error_code else error_code  # noqa: SIM212
    item = PendingKnowledgeItem.create(
        session_id=session_id,
        payload=payload,
        parser_name=parser_name,
        extract_status=extract_status,
        error_code=error_code,
    )
    _store.add(item)
    _sync_task_taskstore_after_prepare(item)
    return item


def prepare_web_search_source(
    query: str,
    *,
    session_id: str,
    provider_override: str = "",
    store: PendingStore | None = None,
) -> PendingKnowledgeItem:
    _store = store or get_pending_store()
    payload, parser_name, error_code = parse_web_search_source(query, provider_override=provider_override, session_id=session_id)
    extract_status = "ok" if not error_code else error_code  # noqa: SIM212
    item = PendingKnowledgeItem.create(
        session_id=session_id,
        payload=payload,
        parser_name=parser_name,
        extract_status=extract_status,
        error_code=error_code,
    )
    _store.add(item)
    return item


# ── commit ────────────────────────────────────────────────────────────────
def commit_pending(
    pending_id: str,
    *,
    store: PendingStore | None = None,
) -> CommitResult:
    """
    用户确认保存：把指定 pending item 写入 V12 knowledge_store。

    流程：
    1. 从 pending store 找到 item
    2. 调 knowledge_store.save_document_text（→ ingest_text → V12 主链）
    3. 标记 committed
    4. 返回 CommitResult

    注意：
    - 不依赖旧 fetch_knowledge_block / retrieve_as_legacy_dicts
    - source_id 使用 payload 中的 source_id（已在 prepare 阶段生成）
    """
    from storage import knowledge_store as ks

    _store = store or get_pending_store()
    item = _store.get(pending_id)

    if item is None:
        return CommitResult(
            success=False,
            pending_id=pending_id,
            source_id="",
            chunk_count=0,
            error_code="pending_not_found",
        )

    if not item.is_committable:
        return CommitResult(
            success=False,
            pending_id=pending_id,
            source_id=item.committed_source_id or "",
            chunk_count=item.committed_chunk_count,
            error_code=f"not_committable:{item.commit_status}:{item.extract_status}",
            title=item.title,
            source_type=item.source_type,
        )

    # 构造 source_id 和 metadata
    # source_id 来自 pending item 的 metadata（prepare 时已生成）
    source_id = item.metadata.get("source_id") or _derive_source_id(item)
    title = item.title
    source_type = item.source_type
    created_at = item.created_at

    try:
        chunk_count = ks.save_document_text(
            item.text,
            source_id=source_id,
            source_type=source_type,
            title=title,
            created_at=created_at,
            extra_metadata=item.metadata,
        )
    except (OSError, ValueError, RuntimeError) as e:
        logger.warning("v13:commit_pending failed pending_id=%s err=%s", pending_id, e)
        return CommitResult(
            success=False,
            pending_id=pending_id,
            source_id=source_id,
            chunk_count=0,
            error_code=f"ingest_error:{type(e).__name__}",
            title=title,
            source_type=source_type,
        )

    _store.mark_committed(
        pending_id,
        committed_source_id=source_id,
        chunk_count=chunk_count,
    )
    _sync_task_taskstore_after_commit(pending_metadata=item.metadata, source_id=source_id)
    logger.info(
        "v13:commit_pending OK pending_id=%s source_id=%s chunks=%d",
        pending_id, source_id, chunk_count,
    )
    return CommitResult(
        success=True,
        pending_id=pending_id,
        source_id=source_id,
        chunk_count=chunk_count,
        title=title,
        source_type=source_type,
    )


def commit_pending_by_session(
    session_id: str,
    *,
    store: PendingStore | None = None,
) -> list[CommitResult]:
    """
    保存当前 session 的所有可提交 pending（跨轮保存场景）。

    返回 CommitResult 列表。
    """
    _store = store or get_pending_store()
    items = _store.list_for_session(session_id, only_committable=True)
    results = []
    for item in items:
        r = commit_pending(item.pending_id, store=_store)
        results.append(r)
    return results


def commit_most_recent_pending(
    session_id: str,
    *,
    store: PendingStore | None = None,
) -> CommitResult:
    """
    保存 session 最近一个可提交 pending（跨轮「保存」最常见场景）。
    """
    _store = store or get_pending_store()
    item = _store.get_recent(session_id, only_committable=True)
    if item is None:
        return CommitResult(
            success=False,
            pending_id="",
            source_id="",
            chunk_count=0,
            error_code="no_pending_found",
        )
    return commit_pending(item.pending_id, store=_store)


# ── list / discard ────────────────────────────────────────────────────────
def list_pending(
    session_id: str,
    *,
    only_committable: bool = True,
    store: PendingStore | None = None,
) -> list[PendingKnowledgeItem]:
    """列出 session 的 pending 资料（默认只列可提交的）。"""
    _store = store or get_pending_store()
    return _store.list_for_session(session_id, only_committable=only_committable)


def discard_pending(
    pending_id: str,
    *,
    store: PendingStore | None = None,
) -> bool:
    """丢弃指定 pending（用户取消）。"""
    _store = store or get_pending_store()
    return _store.discard(pending_id)


# ── 工具函数 ──────────────────────────────────────────────────────────────
def _derive_source_id(item: PendingKnowledgeItem) -> str:
    """从 pending item 的 metadata 或 raw_source 派生 source_id。"""
    # 优先用 prepare 时生成的（在 pending_schema SourcePayload.source_id 里）
    # 但 PendingKnowledgeItem 没有直接存 source_id，从 metadata 取
    meta = item.metadata or {}
    for key in ("source_id", "file_name", "url", "title"):
        v = meta.get(key)
        if v:
            import re
            clean = re.sub(r"[^\w.\-/]+", "_", str(v))[:80]
            return f"{item.source_type}/{clean}"
    return f"{item.source_type}/{item.pending_id[:8]}"


def intent_is_save_request(message: str) -> bool:
    """
    判断用户消息是否含「保存到知识库」意图（最小规则，供 Main / Middle 调用）。

    设计原则：宁可漏判，不能误判（conservative）——只识别明确的保存表达。
    """
    msg = (message or "").strip()
    if not msg:
        return False
    _SAVE_HINTS = (
        "保存到知识库", "存入知识库", "入库", "存到知识库",
        "保存到库", "把这个存", "把它存", "保存下来",
        "以后也要用", "存起来", "保存这个", "save to knowledge",
        "save this",
    )
    lower = msg.lower()
    for hint in _SAVE_HINTS:  # noqa: SIM110
        if hint.lower() in lower:
            return True
    return False
