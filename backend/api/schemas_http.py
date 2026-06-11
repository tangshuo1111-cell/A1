"""API 专用请求/响应模型（与 schemas 业务模型分离，避免 HTTP 细节污染 core）。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# Public task status values returned by GET /tasks/* (see docs/current/contracts/enums.md).
TaskPublicStatus = Literal[
    "queued",
    "running",
    "partial",
    "succeeded",
    "failed",
    "expired",
    "cancelled",
    "pending",
    "timeout",
    "resumed",
]


class ChatRequest(BaseModel):
    message: str = Field(
        ...,
        min_length=1,
        max_length=32000,
        description="用户问题",
    )
    session_id: str | None = Field(None, description="会话 ID，追问需一致")
    use_knowledge: bool = Field(
        False,
        description="是否启用本地样例知识检索（V2 最小闭环；仍走 /chat/agno，无新对外主入口）",
    )
    confirm_long_web_video_asr: bool = Field(
        False,
        description="用户已确认对超长网页视频（超过 V16_WEB_VIDEO_ASR_FALLBACK_MAX_SEC）走 ASR",
    )


class ChatAsyncResponse(BaseModel):
    ok: bool = True
    task_id: str
    session_id: str | None = None
    request_id: str | None = None
    status: str = "pending"
    hint: str | None = None


class ChatResponse(BaseModel):
    ok: bool = True
    task_id: str | None = None
    session_id: str | None = None
    request_id: str | None = None
    answer: str | None = None
    answer_type: str | None = None
    task_status: str | None = None
    has_insufficient_info_notice: bool | None = None
    router_source: str | None = None
    primary_path: str | None = None
    evidence_state: str | None = None
    extra: dict[str, Any] | None = None
    pipeline_ok: bool | None = None
    debug_stage: str | None = None
    error_layer: str | None = None
    pipeline_error_code: str | None = None
    pipeline_hint_zh: str | None = None
    workflow_elapsed_ms: int | None = Field(
        None,
        description="本轮 chat turn 端到端耗时（毫秒），用于区分慢与错",
    )
    interaction_mode_zh: str | None = Field(
        None,
        description="用户可读的本轮交互模式（如知识库检索、读示例文件等）",
    )


class IngestPathsRequest(BaseModel):
    paths: list[str] = Field(default_factory=list, description="相对项目根或绝对路径的文件")


class IngestTextRequest(BaseModel):
    text: str = Field(..., min_length=1)
    source_id: str = Field(..., min_length=1, description="逻辑来源 ID")


class IngestResponse(BaseModel):
    ok: bool = True
    chunks_written: int = 0


class ApiErrorDetail(BaseModel):
    code: str
    message: str
    category: str = ""
    error_layer: str = "api"
    debug_stage: str = "api"


class ErrorResponse(BaseModel):
    ok: bool = False
    error: ApiErrorDetail
    request_id: str | None = None


class TaskStatusResponse(BaseModel):
    ok: bool = True
    task_id: str
    status: str
    raw_status: str = ""
    task_type: str = ""
    source_type: str = ""
    stage: str = ""
    progress: float = 0.0
    session_id: str | None = None
    request_id: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    duration_ms: float = 0.0
    error_code: str = ""
    failure_reason: str = ""
    next_action_hint: str = ""
    result_pending_id: str = ""
    result_source_id: str = ""
    result_ttl_seconds: int = 0
    expires_at: str | None = None
    result_ready: bool = False
    pending_kind: str | None = None
    payload_version: int = 1
    queue_backend: str = ""
    retry_count: int = 0
    task_enqueue_to_finish_ms: int = 0
    result_status: str = ""
    diagnostics: dict[str, Any] | None = None


class TaskResultResponse(TaskStatusResponse):
    ready: bool = False
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None


class SessionTurnSummary(BaseModel):
    task_id: str | None = None
    user_query: str = ""
    task_status: str | None = None
    answer_type: str | None = None


class SessionSummaryResponse(BaseModel):
    ok: bool = True
    session_id: str
    turn_count: int
    recent: list[SessionTurnSummary]


class VideoCookiesFileStatus(BaseModel):
    exists: bool = False
    size_bytes: int = 0
    modified_iso: str | None = None
    domains: list[str] = Field(default_factory=list)
    matched_whitelist_domains: list[str] = Field(default_factory=list)


class VideoCookiesStatusResponse(BaseModel):
    ok: bool = True
    source: str
    effective_path: str | None = None
    managed_path: str
    managed_file: VideoCookiesFileStatus
    whitelist_domains: list[str]
    upload_max_bytes: int


class VideoCookiesMergeInfo(BaseModel):
    new_domains: list[str] = Field(default_factory=list)
    kept_old_domains: list[str] = Field(default_factory=list)
    replaced_domains: list[str] = Field(default_factory=list)


class VideoCookiesUploadResponse(BaseModel):
    ok: bool = True
    managed_path: str
    size_bytes: int
    matched_whitelist_domains: list[str]
    all_domains: list[str]
    hot_reloaded: bool = True
    merge: VideoCookiesMergeInfo


class VideoCookiesDeleteResponse(BaseModel):
    ok: bool = True
    removed: bool
    managed_path: str


class WebVideoMetadataRequest(BaseModel):
    url: str = Field(..., min_length=12, max_length=4000, description="白名单内的视频页 URL（ASCII）")


class WebVideoMetadataResponse(BaseModel):
    """Probe success payload; extra probe fields are allowed."""

    model_config = ConfigDict(extra="allow")

    ok: bool = True
    latency_ms: int | None = None
