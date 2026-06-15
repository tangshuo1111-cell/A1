"""Promote inline document text from user message into v13_text_content."""

from __future__ import annotations

import re
from typing import Final
from urllib.parse import urlparse

_INLINE_DOC_CUE_RE: re.Pattern[str] = re.compile(
    r"(?:"
    r"下面这(?:段|个)?(?:文档|文本|内容)?|"
    r"以下(?:内容|文本|文档)?|"
    r"如下内容|"
    r"给定文本|"
    r"这段(?:文档|文字|内容)|"
    r"基于.+?文档内容"
    r")[，,：:]",
    re.IGNORECASE,
)
_STRONG_INLINE_DOC_CUES: Final[tuple[str, ...]] = (
    "下面这段",
    "以下这段",
    "如下内容",
    "给定文本",
    "这段文档",
    "这段文字",
    "文档内容",
)
_URL_RE: re.Pattern[str] = re.compile(r"https?://[^\s]+", re.IGNORECASE)
_MIN_INLINE_CHARS = 15


def _looks_like_url_payload(text: str) -> bool:
    candidate = (text or "").strip()
    if not candidate:
        return True
    if _URL_RE.fullmatch(candidate):
        return True
    parsed = urlparse(candidate.split()[0])
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def extract_inline_document_from_message(message: str) -> str | None:
    """Split inline document body from a message when no upload/text_content was sent."""
    msg = (message or "").strip()
    if not msg:
        return None

    has_strong_cue = any(cue in msg for cue in _STRONG_INLINE_DOC_CUES) or _INLINE_DOC_CUE_RE.search(msg) is not None
    if not has_strong_cue:
        return None
    if _URL_RE.search(msg) and "下面这段" not in msg and "文档内容" not in msg:
        return None

    body: str | None = None
    for sep in ("：", ":"):
        if sep not in msg:
            continue
        head, tail = msg.rsplit(sep, 1)
        if len(head.strip()) >= 8 and len(tail.strip()) >= _MIN_INLINE_CHARS:
            body = tail.strip()
            break

    if body is None:
        match = _INLINE_DOC_CUE_RE.search(msg)
        if match is not None:
            body = msg[match.end() :].strip()

    if not body or len(body) < _MIN_INLINE_CHARS or _looks_like_url_payload(body):
        return None
    if body == msg:
        return None

    from services.capabilities.document.parse_service import extract_inline_material

    material, _, _ = extract_inline_material(inline_text=body)
    if len((material or "").strip()) < _MIN_INLINE_CHARS:
        return None
    return str(material).strip()


_INLINE_DOCUMENT_MARKER = "[inline_document]"


def append_inline_document_temporary_material(
    materials: list[str],
    *,
    inline_document_text: str | None,
) -> None:
    inline = (inline_document_text or "").strip()
    if not inline:
        return
    if any(str(item).startswith(_INLINE_DOCUMENT_MARKER) for item in materials):
        return
    materials.append(f"{_INLINE_DOCUMENT_MARKER}\n{inline[:2000]}")


def promote_message_inline_document(
    message: str,
    *,
    existing_v13_text: str | None = None,
    existing_file_content: str | bytes | None = None,
) -> str | None:
    if existing_file_content is not None:
        return None
    if (existing_v13_text or "").strip():
        return None
    return extract_inline_document_from_message(message)
