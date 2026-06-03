r"""V9 R3 默认主 chat 路由：`POST /chat/agno`。

身份：**V9 R3 后唯一的公开 chat 主路由**，承载 V6 三强 Agent + V7 视频链 + V8 会话记忆。
- 服务函数：`services.agno_chat_service.run_agno_chat_turn`（无 LangGraph）。
- 前端 `frontend/lib/api.ts: postChat` 默认连本路由。
- 默认 smoke：`scripts\smoke_backend.ps1`、`scripts\smoke_chains.ps1` 均打本路由。
- 旧 `POST /chat`、`POST /chat/async` 已物理删除（V9 R3）；任务查询现由 `GET /tasks/{id}` 契约承担。

V13 R2：新增 `POST /chat/agno/upload`（multipart），支持拖拽文件 prepare 链路。
"""

from __future__ import annotations

import asyncio
import functools
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from api.rate_limit import chat_rate_limit_string, limiter
from api.schemas_http import ChatRequest, ChatResponse
from services import agno_chat_service

router = APIRouter()

# V13 R2：文件上传大小上限（10 MB，本路由当前先覆盖轻量文本与常见办公文档）
_MAX_FILE_BYTES: int = 10 * 1024 * 1024

# V13 R2：支持的文件扩展名（与 document parse service 对齐）
_SUPPORTED_EXTENSIONS: frozenset[str] = frozenset({
    ".txt",
    ".md",
    ".markdown",
    ".docx",
    ".pdf",
    ".xlsx",
    ".xlsm",
})


def _decode_upload_raw_bytes(raw_bytes: bytes) -> str | bytes:
    """在上传链路中只做解码尝试；用于 ``to_thread`` 卸载 CPU，避免大卡事件循环。"""
    for enc in ("utf-8", "utf-8-sig", "gbk"):
        try:
            return raw_bytes.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw_bytes


@router.post("/agno", response_model=ChatResponse)
@limiter.limit(chat_rate_limit_string())
async def post_chat_agno(request: Request, body: ChatRequest) -> ChatResponse:
    """V1 默认基础问答入口：只走 agno_chat_service，不经 LangGraph。

    生产版第二轮（B-007）：路由 async；主链同步函数在线程池执行，避免阻塞事件循环。
    """
    rid = getattr(request.state, "request_id", None)
    runner = functools.partial(
        agno_chat_service.run_agno_chat_turn,
        body.message,
        session_id=body.session_id,
        request_id=rid,
        use_knowledge=body.use_knowledge,
        confirm_long_web_video_asr=body.confirm_long_web_video_asr,
    )
    out = await asyncio.to_thread(runner)
    return ChatResponse.model_validate(out)


@router.post("/agno/upload", response_model=ChatResponse)
@limiter.limit(chat_rate_limit_string())
async def post_chat_agno_upload(
    request: Request,
    message: str = Form(..., min_length=1, max_length=32000,
                        description="用户问题（与 /agno 的 message 字段含义一致）"),
    session_id: str | None = Form(None, description="会话 ID，追问需一致"),
    use_knowledge: bool = Form(False, description="是否启用本地样例知识检索"),
    confirm_long_web_video_asr: bool = Form(
        False,
        description="用户已确认对超长网页视频走 ASR（与 JSON /chat/agno 同名字段）",
    ),
    file: UploadFile = File(..., description="待 prepare 的文件（如 .txt/.md/.docx/.pdf/.xlsx，≤ 10 MB）"),  # noqa: B008
) -> ChatResponse:
    """V13 R2 拖拽文件入口：multipart 上传文本/常见办公文件，触发文件 prepare 链路。

    请求格式：multipart/form-data
      - message:       用户说的话（如"先帮我解析这个文件"）
      - session_id:    会话 ID（可选，跨轮保存需一致）
      - use_knowledge: 是否同时检索知识库（默认 false）
      - file:          支持的文件（≤ 10 MB）

    响应：与 POST /chat/agno 完全相同的 ChatResponse 结构。
    extra 字段会额外包含：
      - pending_kind: "material_pending" / "processing_pending" / ...
      - pending_source_id: 当前待保存材料的 pending_id（如存在）
      - pending_preview: 待保存材料的标题、来源类型与元信息摘要

    解析状态说明（extra.pending_preview.metadata.extract_status）：
      - ok:                 解析成功，资料已进入 pending，可在后续轮次中说「保存到知识库」
      - unsupported_format: 不支持的文件格式（当前只支持 .txt / .md）
      - file_not_found:     文件内容为空
      - parse_failed:       解析过程出错
      - empty_content:      解析成功但内容为空
    """
    rid = getattr(request.state, "request_id", None)

    # 1) 文件名与扩展名校验（在读取内容前做，避免浪费）
    filename = (file.filename or "").strip()
    if not filename:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "MISSING_FILENAME",
                "message": "上传文件缺少文件名，请检查请求。",
            },
        )
    ext = Path(filename).suffix.lower()
    if ext not in _SUPPORTED_EXTENSIONS:
        # 不支持的格式：仍走链路，让 prepare_file_source 返回 unsupported_format 状态
        # 这样前端可以看到文件卡片 + 明确的 unsupported_format 解析状态
        # （不直接 reject，给用户可读的文件卡片反馈，而不是原始 HTTP 错误）
        pass  # 下面继续读取，middle 会返回 unsupported_format 状态

    # 2) 读取文件内容（限制大小）
    raw_bytes = await file.read(_MAX_FILE_BYTES + 1)
    if len(raw_bytes) > _MAX_FILE_BYTES:
        raise HTTPException(
            status_code=413,
            detail={
                "code": "FILE_TOO_LARGE",
                "message": f"文件大小超过限制（最大 {_MAX_FILE_BYTES // 1024 // 1024} MB）。",
            },
        )
    if not raw_bytes:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "EMPTY_FILE",
                "message": "上传的文件内容为空。",
            },
        )

    # 3) UTF-8 / GBK 解码卸载到线程池（B-008）
    file_content: str | bytes = await asyncio.to_thread(_decode_upload_raw_bytes, raw_bytes)

    # 4) 将完整文件名作为 v13_title，保留扩展名供下游 parser 判别
    title = filename

    # 5) 调用主链（与 post_chat_agno 一致，额外传入 v13_file_content）
    runner = functools.partial(
        agno_chat_service.run_agno_chat_turn,
        message,
        session_id=session_id,
        request_id=rid,
        use_knowledge=use_knowledge,
        v13_file_content=file_content,
        v13_title=title,
        confirm_long_web_video_asr=confirm_long_web_video_asr,
    )
    out = await asyncio.to_thread(runner)
    return ChatResponse.model_validate(out)
