from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Final
from urllib.parse import urlparse

_URL_RE = re.compile(r"https?://[^\s]+", re.IGNORECASE)
_VIDEO_HOST_HINTS = (
    "bilibili.com",
    "youtube.com",
    "youtu.be",
    "v.qq.com",
    "youku.com",
    "ixigua.com",
)
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


@dataclass(frozen=True)
class RequestSignals:
    urls: tuple[str, ...]
    has_video_url: bool
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
    urls = tuple(_URL_RE.findall(msg))
    parsed_hosts = tuple((urlparse(url).netloc or "").lower() for url in urls)
    has_video_url = any(any(hint in host for hint in _VIDEO_HOST_HINTS) for host in parsed_hosts)
    has_web_url = bool(urls) and not has_video_url
    normalized_attachments = _normalize_attachments(attachments)
    attachment_names = " ".join(str(item.get("name") or "") for item in normalized_attachments).lower()
    attachment_types = {str(item.get("type") or "") for item in normalized_attachments}
    has_video_attachment = any(hint in attachment_names for hint in _VIDEO_FILE_HINTS)
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
    has_kb_intent = use_knowledge or any(token.lower() in lower for token in _KB_HINTS)
    has_web_intent = has_web_url or any(token in lower for token in _WEB_HINTS)
    has_ocr_intent = any(token in lower for token in _OCR_HINTS)
    has_long_video_hint = "长视频" in msg or "后台" in msg or "youtube.com" in lower or "youtu.be" in lower
    has_mixed_evidence_intent = any(token in msg for token in _MIXED_EVIDENCE_HINTS)
    asks_background_processing = any(token in msg for token in ("后台", "异步", "稍后", "先排队", "先挂起", "长任务"))
    has_complex_intent = sum(1 for token in _COMPLEX_HINTS if token in msg) >= 1 or len(urls) > 1
    source_kinds_count = sum(
        1 for flag in (
            has_video_url or has_video_attachment,
            has_document_payload and not has_video_attachment,
            has_web_intent,
            has_kb_intent,
        ) if flag
    )
    return RequestSignals(
        urls=urls,
        has_video_url=has_video_url,
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
