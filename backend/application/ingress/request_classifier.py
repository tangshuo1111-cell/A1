from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Final

_URL_RE = re.compile(r"https?://[^\s]+", re.IGNORECASE)
_ASCII_DOC_EXT_RE: re.Pattern[str] = re.compile(
    r"\b(?:pdf|docx?|xlsx?|pptx?|markdown|md)\b",
    re.IGNORECASE,
)
_CHINESE_DOC_HINTS: Final[tuple[str, ...]] = ("文档", "文件", "附件")
_DOC_ACTION_HINTS = ("解析", "提取")
_WEB_HINTS = ("网页", "页面", "网站", "阅读", "抓取", "上网", "联网", "搜索", "搜一下", "查询")
_KB_HINTS = ("知识库", "样例", "数据库要求", "根据知识库", "资料库", "RAG")
_COMPLEX_HINTS = ("对比", "比较", "综合", "多来源", "分别", "同时", "然后", "并给出", "评估")
_VIDEO_FILE_HINTS = (".mp4", ".mov", ".mkv", ".avi", ".webm")
_OCR_HINTS = ("扫描版", "ocr", "识别", "按章节", "提取重点")
_MIXED_EVIDENCE_HINTS = ("网页证据", "知识库和网页", "结合知识库", "网页和知识库", "多方证据")
_VIDEO_INTENT_HINTS: Final[tuple[str, ...]] = (
    "总结这个视频",
    "总结以下视频",
    "这个视频",
    "该视频",
    "这段视频",
    "本视频",
    "短视频",
    "录像",
    "影片",
)
_WEBPAGE_INTENT_OVERRIDES: Final[tuple[str, ...]] = (
    "网页",
    "页面",
    "网站",
    "这篇文章",
    "这个链接",
    "该链接",
)


@dataclass(frozen=True)
class RequestSignals:
    urls: tuple[str, ...]
    has_video_url: bool
    has_unsupported_video_url: bool
    has_video_attachment: bool
    has_web_url: bool
    has_document_payload: bool
    has_document_intent: bool
    has_kb_intent: bool
    has_web_intent: bool
    has_complex_intent: bool
    has_ocr_intent: bool
    has_long_video_hint: bool
    has_mixed_evidence_intent: bool
    asks_background_processing: bool
    source_kinds_count: int
    attachment_count: int


def _normalize_url_token(url: str) -> str:
    return url.rstrip(".,;:)]}>")


def _has_explicit_video_intent(message: str) -> bool:
    msg = (message or "").strip()
    if not msg:
        return False
    if any(token in msg for token in _WEBPAGE_INTENT_OVERRIDES):
        return False
    lower = msg.lower()
    if any(token in msg for token in _VIDEO_INTENT_HINTS):
        return True
    if "视频" in msg:
        return True
    return bool(re.search(r"\bvideo\b", lower))


def _normalize_attachments(attachments: list[dict[str, Any]] | None) -> tuple[dict[str, Any], ...]:
    return tuple(attachments or ())


def _has_document_intent_from_message(
    message: str,
    *,
    attachment_names: str,
) -> bool:
    lower = (message or "").lower()
    if any(token in lower for token in _CHINESE_DOC_HINTS):
        return True
    text_without_urls = _URL_RE.sub(" ", message or "")
    if _ASCII_DOC_EXT_RE.search(text_without_urls):
        return True
    return bool(_ASCII_DOC_EXT_RE.search(attachment_names))


def _is_about_kb_strategy_question(message: str) -> bool:
    """Discussing KB product/workflow — not querying KB for facts."""
    msg = (message or "").strip()
    if not msg:
        return False
    lower = msg.lower()
    if any(q in msg for q in ("根据知识库", "查知识库", "检索知识库", "从知识库", "知识库里关于")):
        return False
    if "知识库" not in msg and "rag" not in lower:
        return False
    strategy_markers = (
        "产品策略",
        "收录",
        "沉淀",
        "用户确认",
        "全量自动",
        "知识库问答",
        "知识库规模",
        "复用率",
        "冷启动",
        "长期维护",
        "确认后再收录",
        "自动沉淀",
    )
    return any(m in msg for m in strategy_markers)


def classify_request(
    *,
    message: str,
    use_knowledge: bool,
    v13_file_content: str | bytes | None,
    v13_text_content: str | None,
    attachments: list[dict[str, Any]] | None = None,
) -> RequestSignals:
    msg = (message or "").strip()
    lower = msg.lower()
    urls = tuple(_normalize_url_token(u) for u in _URL_RE.findall(msg))
    from video.url_fetch import is_supported_video_url

    has_video_url = any(is_supported_video_url(url) for url in urls)
    has_explicit_video_intent = _has_explicit_video_intent(msg)
    has_unsupported_video_url = bool(urls) and has_explicit_video_intent and not has_video_url
    normalized_attachments = _normalize_attachments(attachments)
    attachment_names = " ".join(str(item.get("name") or "") for item in normalized_attachments).lower()
    attachment_types = {str(item.get("type") or "") for item in normalized_attachments}
    has_video_attachment = any(hint in attachment_names for hint in _VIDEO_FILE_HINTS)
    has_web_url = bool(urls) and not has_video_url and not has_unsupported_video_url
    has_document_payload = (
        v13_file_content is not None
        or bool((v13_text_content or "").strip())
        or bool(normalized_attachments)
    )
    has_document_intent = _has_document_intent_from_message(msg, attachment_names=attachment_names)
    if not has_document_intent and has_document_payload and any(token in lower for token in _DOC_ACTION_HINTS):
        has_document_intent = True
    if "local_file" in attachment_types:
        has_document_intent = True
    has_kb_intent = use_knowledge or (
        any(token.lower() in lower for token in _KB_HINTS)
        and not _is_about_kb_strategy_question(msg)
    )
    has_web_intent = (has_web_url or any(token in lower for token in _WEB_HINTS)) and not has_unsupported_video_url
    has_ocr_intent = any(token in lower for token in _OCR_HINTS)
    has_long_video_hint = "长视频" in msg or "后台" in msg or "youtube.com" in lower or "youtu.be" in lower
    has_mixed_evidence_intent = any(token in msg for token in _MIXED_EVIDENCE_HINTS)
    asks_background_processing = any(token in msg for token in ("后台", "异步", "稍后", "先排队", "先挂起", "长任务"))
    has_complex_intent = sum(1 for token in _COMPLEX_HINTS if token in msg) >= 1 or len(urls) > 1
    source_kinds_count = sum(
        1 for flag in (
            has_video_url or has_video_attachment or has_unsupported_video_url,
            has_document_payload and not has_video_attachment,
            has_web_intent,
            has_kb_intent,
        ) if flag
    )
    return RequestSignals(
        urls=urls,
        has_video_url=has_video_url,
        has_unsupported_video_url=has_unsupported_video_url,
        has_video_attachment=has_video_attachment,
        has_web_url=has_web_url,
        has_document_payload=has_document_payload,
        has_document_intent=has_document_intent,
        has_kb_intent=has_kb_intent,
        has_web_intent=has_web_intent,
        has_complex_intent=has_complex_intent,
        has_ocr_intent=has_ocr_intent,
        has_long_video_hint=has_long_video_hint,
        has_mixed_evidence_intent=has_mixed_evidence_intent,
        asks_background_processing=asks_background_processing,
        source_kinds_count=source_kinds_count,
        attachment_count=len(normalized_attachments),
    )
