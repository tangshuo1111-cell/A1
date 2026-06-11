"""
V13 R1：统一资料生命周期 schema。

定义：
- SourcePayload：来自各来源（text / file / web_url / local_video / web_video）的统一中间 payload
- PendingKnowledgeItem：统一 pending 对象，跨来源可比较
- 三态常量：TEMPORARY / PENDING / COMMITTED

设计原则：
- 所有来源先变成 SourcePayload，再进入 PendingKnowledgeItem
- PendingKnowledgeItem 是跨轮可找回的最小单元
- commit 后调用 V12 knowledge_store.save_document_text → ingest_text 入库
- 不新建第二套知识库；不复活旧 retrieve_as_legacy_dicts / fetch_knowledge_block 路径

V13 R2：
- local_video / web_video 已并入统一生命周期（SOURCE_TYPE_LOCAL_VIDEO / SOURCE_TYPE_WEB_VIDEO）
- PendingVideoText 降级为 V11 兼容层，默认主路径使用 PendingKnowledgeItem
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

# ── 来源类型常量 ──────────────────────────────────────────────────────────
SOURCE_TYPE_TEXT = "text"
SOURCE_TYPE_TEXT_FILE = "text_file"          # .txt / .md 等纯文本型文件
SOURCE_TYPE_WEB_URL = "web_url"
SOURCE_TYPE_LOCAL_VIDEO = "local_video"      # 本地 .mp4 等视频文件（MCP 文本化）
SOURCE_TYPE_WEB_VIDEO = "web_video"          # 网页/视频站 URL（字幕/ASR 文本化）
SOURCE_TYPE_OCR_DOCUMENT = "ocr_document"
SOURCE_TYPE_ASR_TRANSCRIPT = "asr_transcript"
SOURCE_TYPE_WEB_SEARCH = "web_search"
# V16 R1：文档类来源类型（各有专属 metadata）
SOURCE_TYPE_DOCX = "docx"                    # Word .docx（段落/标题/表格）
SOURCE_TYPE_XLSX = "xlsx"                    # Excel .xlsx（sheet/行列）
SOURCE_TYPE_PDF = "pdf"                      # PDF（文本 PDF + 扫描 PDF 检测）

# ── 生命周期三态 ──────────────────────────────────────────────────────────
STATUS_TEMPORARY = "temporary"    # 刚进入当前轮，未 prepare/pending，当前轮可用于回答
STATUS_PENDING = "pending"        # 已 prepare，可 preview，等待用户确认保存
STATUS_COMMITTED = "committed"    # 已入库，可被 V12 retrieval 命中
STATUS_FAILED = "failed"          # prepare / commit 失败
STATUS_DISCARDED = "discarded"    # 用户取消或 pending 过期

# PendingKind string values (align with application.chat.pending_kind.PendingKind)
PENDING_KIND_NONE = "none"
PENDING_KIND_FAST_PENDING = "fast_pending"
PENDING_KIND_PROCESSING_PENDING = "processing_pending"
PENDING_KIND_MATERIAL_PENDING = "material_pending"
PENDING_KIND_PARTIAL_PENDING = "partial_pending"
PENDING_KIND_COMMITTED = "committed"


def derive_pending_kind(
    *,
    extract_status: str,
    commit_status: str,
    error_code: str = "",
) -> str:
    """Single semantic mapping from lifecycle fields → pending_kind (§9.3 / S10a)."""
    if commit_status == STATUS_COMMITTED:
        return PENDING_KIND_COMMITTED
    if commit_status == STATUS_DISCARDED:
        return PENDING_KIND_NONE
    if extract_status in {"queued", "processing", "running"}:
        return PENDING_KIND_PROCESSING_PENDING
    if extract_status in {"partial", "parse_partial"}:
        return PENDING_KIND_PARTIAL_PENDING
    if commit_status == STATUS_PENDING and extract_status == "ok":
        return PENDING_KIND_MATERIAL_PENDING
    if error_code or extract_status in {"parse_failed", "empty_content", "failed"}:
        return PENDING_KIND_PARTIAL_PENDING
    return PENDING_KIND_NONE


# ── 统一 payload ──────────────────────────────────────────────────────────
@dataclass(frozen=True)
class SourcePayload:
    """所有来源的统一中间结构体，parser 产出后统一进入此格式。

    V13 R1 字段：
    - source_type  : 来源类型（text / text_file / web_url）
    - source_id    : 入库时使用的标识，格式由来源类型决定
    - title        : 资料标题（来自文件名 / 网页 <title> / 用户提供）
    - text         : 清洗后的正文（prepare 产出的 plain text）
    - metadata     : 结构化元信息（见下文）
    - raw_source   : 原始来源标识（URL / 文件路径 / 空字符串）

    metadata 统一字段（V13 R1 最小集）：
    - title / name
    - url / file_path
    - parser_name
    - created_at
    - chunk_index（commit 后可由 ingest 产出，prepare 阶段为 0）
    """

    source_type: str
    source_id: str
    title: str
    text: str
    metadata: dict[str, Any]
    raw_source: str = ""

    def preview_text(self, max_chars: int = 500) -> str:
        """返回正文预览（最多 max_chars 字）。"""
        t = (self.text or "").strip()
        if len(t) <= max_chars:
            return t
        return t[:max_chars] + "…"


# ── PendingKnowledgeItem ──────────────────────────────────────────────────
@dataclass
class PendingKnowledgeItem:
    """统一 pending 对象，所有来源（text / text_file / web_url）共用同一结构。

    生命周期：PENDING → COMMITTED（commit 后）/ DISCARDED（用户取消/过期）

    V13 R1：仅在内存中，不持久化。生命周期与 session 同步。
    V13 R2：可考虑 SQLite 持久化，支持服务重启后找回。
    """

    pending_id: str
    session_id: str
    source_type: str
    title: str
    raw_source: str
    text: str
    preview_text: str
    metadata: dict[str, Any]
    parser_name: str
    extract_status: str           # "ok" / "parse_failed" / "empty_content" 等
    error_code: str               # 失败时的结构化错误码
    created_at: str
    commit_status: str            # STATUS_PENDING / STATUS_COMMITTED / STATUS_DISCARDED
    pending_kind: str = ""        # S10a — canonical pending semantics for callers

    # commit 后填充
    committed_source_id: str = ""
    committed_chunk_count: int = 0

    @classmethod
    def create(
        cls,
        *,
        session_id: str,
        payload: SourcePayload,
        parser_name: str,
        extract_status: str = "ok",
        error_code: str = "",
    ) -> PendingKnowledgeItem:
        """从统一 SourcePayload 构造 pending 对象。"""
        now = datetime.now(tz=UTC).isoformat()
        preview = payload.preview_text(max_chars=400)
        # 把 payload.source_id 存入 metadata，供 commit 时取用
        meta = dict(payload.metadata)
        meta["source_id"] = payload.source_id
        return cls(
            pending_id=str(uuid.uuid4()),
            session_id=session_id or "__default__",
            source_type=payload.source_type,
            title=payload.title,
            raw_source=payload.raw_source,
            text=payload.text,
            preview_text=preview,
            metadata=meta,
            parser_name=parser_name,
            extract_status=extract_status,
            error_code=error_code,
            created_at=now,
            commit_status=STATUS_PENDING,
            pending_kind=derive_pending_kind(
                extract_status=extract_status,
                commit_status=STATUS_PENDING,
                error_code=error_code,
            ),
        )

    def sync_pending_kind(self) -> None:
        """Refresh pending_kind from current lifecycle fields."""
        self.pending_kind = derive_pending_kind(
            extract_status=self.extract_status,
            commit_status=self.commit_status,
            error_code=self.error_code,
        )

    @property
    def is_committable(self) -> bool:
        return self.commit_status == STATUS_PENDING and self.extract_status == "ok"

    @property
    def is_committed(self) -> bool:
        return self.commit_status == STATUS_COMMITTED

    def to_trace_dict(self) -> dict[str, Any]:
        """供 trace / extra 输出的结构化字典（不含完整 text）。"""
        return {
            "pending_id": self.pending_id,
            "source_type": self.source_type,
            "title": self.title,
            "parser_name": self.parser_name,
            "extract_status": self.extract_status,
            "error_code": self.error_code,
            "commit_status": self.commit_status,
            "pending_kind": self.pending_kind or derive_pending_kind(
                extract_status=self.extract_status,
                commit_status=self.commit_status,
                error_code=self.error_code,
            ),
            "committed_source_id": self.committed_source_id,
            "committed_chunk_count": self.committed_chunk_count,
            "preview_text": self.preview_text[:200] if self.preview_text else "",
        }


_PENDING_ITEM_FIELDS = (
    "pending_id",
    "session_id",
    "source_type",
    "title",
    "raw_source",
    "text",
    "preview_text",
    "metadata",
    "parser_name",
    "extract_status",
    "error_code",
    "created_at",
    "commit_status",
    "pending_kind",
    "committed_source_id",
    "committed_chunk_count",
)


def pending_item_to_dict(item: PendingKnowledgeItem) -> dict[str, Any]:
    """Serialize pending item for PG persistence (Round 7)."""
    return asdict(item)


def pending_item_from_dict(data: dict[str, Any]) -> PendingKnowledgeItem:
    """Deserialize pending item from PG payload_json."""
    kwargs = {k: data[k] for k in _PENDING_ITEM_FIELDS if k in data}
    return PendingKnowledgeItem(**kwargs)
