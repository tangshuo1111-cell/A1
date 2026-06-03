"""
静态 HTML 正文优先抽取（web fast path / 静态入库共用）。

策略：正文容器评分 → 通用噪音块删除 → 文首 TOC 裁剪 → 保守尾部裁剪 → 整页回退；
质量仍差时在同一入口内单次 trafilatura 回退。
"""

from __future__ import annotations

import logging
import re
from typing import Final

logger = logging.getLogger("light_maqa")

_MAX_PLAIN_CHARS: Final[int] = 200_000

# 保守尾部裁剪：仅在正文已足够长、且 marker 出现在后段时才截断。
_MIN_CHARS_FOR_TAIL_TRIM: Final[int] = 300
_TAIL_TRIM_MIN_BODY_RATIO: Final[float] = 0.55
_MAX_LEADING_CATEGORY_CHARS: Final[int] = 12
_MIN_HEADLINE_CHARS: Final[int] = 15
_HEADER_ECHO_SCAN_LINES: Final[int] = 8
_MAX_BYLINE_CHARS: Final[int] = 16
_DATE_LINE_RE: Final[re.Pattern[str]] = re.compile(
    r"^\d{4}年\d{1,2}月\d{1,2}日"
)
_SENTENCE_END_RE: Final[re.Pattern[str]] = re.compile(r"[。！？.!?」』\"']$")
_CONTINUATION_END_RE: Final[re.Pattern[str]] = re.compile(r"[，、：；]$")
_MAX_MERGE_FRAGMENT_CHARS: Final[int] = 20
_ORPHAN_LIST_MARKER_RE: Final[re.Pattern[str]] = re.compile(r"^\d{1,2}\.$")
_INLINE_LIST_MARKER_SUFFIX_RE: Final[re.Pattern[str]] = re.compile(r"[：:]\s*\d{1,2}\.$")
_MARKDOWN_ONLY_HEADING_RE: Final[re.Pattern[str]] = re.compile(r"^#+\s*$")
_MAX_TOC_LINE_CHARS: Final[int] = 36
_MIN_BODY_PARAGRAPH_CHARS: Final[int] = 48
_NAV_BLOB_MIN_CHARS: Final[int] = 32
_MIN_TOC_LINES_TO_TRIM: Final[int] = 4
_MIN_QUALITY_BODY_CHARS: Final[int] = 120
_QUALITY_FALLBACK_THRESHOLD: Final[float] = 0.35
_PHOTO_CREDIT_RE: Final[re.Pattern[str]] = re.compile(
    r"(Associated Press|Reuters|Getty Images|Agence France-Presse|\bAFP\b|Bloomberg|"
    r"Shutterstock|European Pressphoto Agency|\bEPA\b)",
    re.IGNORECASE,
)
_PHOTO_CREDIT_NAME_AGENCY_RE: Final[re.Pattern[str]] = re.compile(
    r"^[A-Za-z][A-Za-z .'\-]*/[A-Za-z][A-Za-z .'\-]*$"
)
_STANDALONE_AD_MARKERS: Final[tuple[str, ...]] = (
    "广告",
    "Advertisement",
    "Sponsored Content",
    "Sponsored",
    "Paid Post",
    "付费推广",
)
_HIGH_CONFIDENCE_TAIL_MARKERS: Final[tuple[str, ...]] = (
    "相关内容",
    "相关文章",
    "推荐阅读",
    "更多阅读",
    "评论区",
    "This item is part of",
    "Related Stories",
    "Related Articles",
    "More Stories",
    "Read More",
    "向他人分享",
    "下载 PDF",
    "Download PDF",
    "Download as PDF",
    "Share this page",
    "Share this article",
    "Was this page helpful",
    "Was this helpful",
)

_CONTENT_CONTAINER_SELECTORS: Final[tuple[str, ...]] = (
    "article",
    "main",
    "[role='main']",
    ".article",
    ".article-content",
    ".article-body",
    ".story-body",
    ".post-content",
    ".entry-content",
    ".content__body",
    ".body-container",
)

_NOISE_TAG_SELECTORS: Final[str] = (
    "nav, header, footer, aside, form, button, input, select, textarea, "
    "figure, figcaption, "
    "[role='navigation'], [role='banner'], [role='contentinfo'], "
    ".share, .sharing, .social, .social-share, .toolbar, .breadcrumb, .breadcrumbs, "
    ".print, .print-options, .comments, .comment, .sidebar, .related, .recommend, "
    ".ad, .ads, .advertisement, .promo, .sponsored, "
    "[class*='caption'], [class*='image-credit'], [class*='photo-credit'], "
    "[class*='advert'], [id*='advert'], [class*='sponsor'], [data-testid*='ad'], "
    ".toc, .table-of-contents, .docs-sidebar, .doc-sidebar, .sidebar-nav, "
    ".menu-inline, [role='complementary']"
)

_PAGE_LEVEL_NOISE_SELECTORS: Final[str] = (
    "nav, header, footer, aside, [role='navigation'], [role='banner'], "
    "[role='contentinfo'], .docs-sidebar, .doc-sidebar, .sidebar-nav, "
    ".toc, .table-of-contents, [role='complementary']"
)


def line_is_ad_marker(line: str) -> bool:
    text = (line or "").strip()
    if not text:
        return False
    lower = text.lower()
    for marker in _STANDALONE_AD_MARKERS:
        marker_lower = marker.lower()
        if text == marker or lower == marker_lower:
            return True
        if lower.startswith(marker_lower) and len(text) <= len(marker) + 12:
            return True
    return False


def line_is_photo_credit_or_caption(line: str) -> bool:
    text = (line or "").strip()
    if not text or len(text) > 120:
        return False
    if _PHOTO_CREDIT_RE.search(text):
        return True
    if _PHOTO_CREDIT_NAME_AGENCY_RE.match(text):
        return True
    lower = text.lower()
    if lower.startswith("photo:") or lower.startswith("photograph:"):
        return True
    return bool(text.startswith("图片说明：") or text.startswith("图："))


def line_is_generic_chrome(line: str) -> bool:
    """通用 UI 噪音行（非站点导航词表）。"""
    text = (line or "").strip()
    if not text:
        return True
    if line_is_ad_marker(text) or line_is_photo_credit_or_caption(text):
        return True
    if len(text) <= 2 and text in {"上一页", "下一页", "关闭", "评论", "打印", "分享"}:
        return True
    noisy_prefixes = (
        "无障碍链接",
        "跳转到内容",
        "跳转到导航",
        "跳转到检索",
        "Print Options",
        "Link has been copied to clipboard",
        "复制链接",
        "点击显示",
    )
    if any(text.startswith(prefix) for prefix in noisy_prefixes):
        return True
    if len(text) <= 24 and text in {
        "Facebook",
        "Twitter",
        "WhatsApp",
        "Telegram",
        "Email",
        "Line",
        "分享",
    }:
        return True
    return bool(_MARKDOWN_ONLY_HEADING_RE.fullmatch(text))


def line_is_orphan_list_marker(line: str) -> bool:
    return bool(_ORPHAN_LIST_MARKER_RE.match((line or "").strip()))


def line_invites_list_continuation(line: str) -> bool:
    text = (line or "").strip()
    if not text:
        return False
    if line_is_orphan_list_marker(text):
        return True
    return bool(_INLINE_LIST_MARKER_SUFFIX_RE.search(text))


def should_merge_broken_line(previous: str, current: str) -> bool:
    prev = (previous or "").strip()
    curr = (current or "").strip()
    if not prev or not curr:
        return False
    if line_is_orphan_list_marker(curr):
        return False
    if line_invites_list_continuation(prev):
        return not (line_is_header_metadata(curr) or line_is_standalone_byline(curr) or line_is_ad_marker(curr) or line_is_photo_credit_or_caption(curr) or line_matches_tail_marker(curr))
    if len(curr) == 1 and curr in "，、；：":
        return True
    if len(curr) > _MAX_MERGE_FRAGMENT_CHARS:
        return False
    if _SENTENCE_END_RE.search(prev) and not _CONTINUATION_END_RE.search(prev):
        return False
    if (
        line_is_header_metadata(curr)
        or line_is_standalone_byline(curr)
        or line_is_ad_marker(curr)
        or line_is_photo_credit_or_caption(curr)
        or line_matches_tail_marker(curr)
    ):
        return False
    return not (len(prev) >= _MIN_HEADLINE_CHARS and curr == prev)


def merge_broken_lines(lines: list[str]) -> list[str]:
    if not lines:
        return lines
    out: list[str] = [lines[0]]
    for curr in lines[1:]:
        if should_merge_broken_line(out[-1], curr):
            out[-1] = out[-1] + curr
        else:
            out.append(curr)
    return out


def merge_broken_lines_stable(lines: list[str]) -> list[str]:
    prev_len = -1
    while len(lines) != prev_len:
        prev_len = len(lines)
        lines = merge_broken_lines(lines)
    return lines


def line_is_standalone_byline(line: str) -> bool:
    text = (line or "").strip()
    if not text or len(text) > _MAX_BYLINE_CHARS:
        return False
    if text.endswith("记者"):
        return True
    lower = text.lower()
    return lower.startswith("by ") or lower.endswith(" reporter")


def line_is_header_metadata(line: str) -> bool:
    text = (line or "").strip()
    if not text:
        return False
    if _DATE_LINE_RE.match(text):
        return True
    if re.search(r"\d", text):
        return False
    return bool(2 <= len(text) <= 4 and not any(ch in text for ch in "。！？，、；：（）()"))


def collapse_adjacent_duplicate_lines(lines: list[str]) -> list[str]:
    if not lines:
        return lines
    out = [lines[0]]
    for ln in lines[1:]:
        if ln != out[-1]:
            out.append(ln)
    return out


def drop_leading_orphan_category(lines: list[str]) -> list[str]:
    """去掉独立分类标签：仅当后续标题行在文首区重复出现时才裁首行。"""
    if len(lines) < 3:
        return lines
    first, second = lines[0], lines[1]
    if len(first) > _MAX_LEADING_CATEGORY_CHARS or len(second) < _MIN_HEADLINE_CHARS:
        return lines
    head = lines[2 : min(_HEADER_ECHO_SCAN_LINES, len(lines))]
    if second not in head:
        return lines
    if first in head:
        return lines
    return lines[1:]


def drop_header_zone_duplicate_title(lines: list[str]) -> list[str]:
    scan = min(_HEADER_ECHO_SCAN_LINES, len(lines))
    drop: set[int] = set()
    for i in range(scan):
        title = lines[i]
        if len(title) < _MIN_HEADLINE_CHARS:
            continue
        for j in range(i + 1, scan):
            if j in drop or lines[j] != title:
                continue
            between = lines[i + 1 : j]
            if between and all(line_is_header_metadata(ln) for ln in between):
                drop.add(j)
    if not drop:
        return lines
    return [ln for idx, ln in enumerate(lines) if idx not in drop]


def trim_trailing_header_echo(lines: list[str]) -> list[str]:
    if len(lines) < 4:
        return lines
    if sum(len(ln) for ln in lines) < _MIN_CHARS_FOR_TAIL_TRIM:
        return lines

    max_head = min(_HEADER_ECHO_SCAN_LINES, len(lines) // 3)
    max_k = min(4, len(lines) // 3)
    trimmed = False
    for k in range(max_k, 0, -1):
        if trimmed:
            break
        suffix = lines[-k:]
        for i in range(0, max_head):
            if lines[i : i + k] == suffix and i + k <= len(lines) - k:
                lines = lines[:-k]
                trimmed = True
                break
        if trimmed:
            break
        if k >= 2 and line_is_standalone_byline(suffix[-1]):
            for i in range(0, max_head):
                if lines[i : i + k - 1] == suffix[: k - 1] and i + k - 1 <= len(lines) - k:
                    lines = lines[:-k]
                    trimmed = True
                    break

    if line_is_standalone_byline(lines[-1]) and len(lines) >= 6:
        lines = lines[:-1]
    if (
        len(lines) >= 5
        and len(lines[0]) >= _MIN_HEADLINE_CHARS
        and lines[-1] == lines[0]
        and sum(len(ln) for ln in lines) >= _MIN_CHARS_FOR_TAIL_TRIM
    ):
        lines = lines[:-1]
    return lines


def line_looks_like_toc_entry(line: str) -> bool:
    text = (line or "").strip()
    if not text or len(text) > _MAX_TOC_LINE_CHARS:
        return False
    if len(text) >= _MIN_HEADLINE_CHARS:
        return False
    if line_is_header_metadata(text) or line_is_standalone_byline(text):
        return False
    if re.match(r"^[A-Z][A-Z .'\-]{2,40}$", text):
        return False
    if _SENTENCE_END_RE.search(text):
        return False
    return not any(ch in text for ch in "。！？.!?")


def line_looks_like_nav_blob(line: str) -> bool:
    """长行但无句读，常见于文档站侧栏/目录拼接。"""
    text = (line or "").strip()
    if not text:
        return False
    if re.search(r"[。！？.!?]", text):
        return False
    if len(text) >= _NAV_BLOB_MIN_CHARS:
        return True
    parts = text.split()
    return len(parts) >= 4 and all(len(part) <= 12 for part in parts)


def line_looks_like_body_paragraph(line: str) -> bool:
    text = (line or "").strip()
    if not text:
        return False
    if len(text) >= _MIN_BODY_PARAGRAPH_CHARS:
        return True
    return bool(len(text) >= 24 and (_SENTENCE_END_RE.search(text) or text.count("，") >= 1 or text.count(",") >= 1))


def trim_leading_toc_block(lines: list[str]) -> list[str]:
    if len(lines) < 2:
        return lines

    start = 0
    while start < len(lines):
        current = lines[start]
        if line_looks_like_body_paragraph(current):
            break
        if line_looks_like_nav_blob(current) or line_looks_like_toc_entry(current):
            start += 1
            continue
        if (
            len(current) <= 20
            and start + 1 < len(lines)
            and line_looks_like_body_paragraph(lines[start + 1])
        ):
            break
        if start >= _MIN_TOC_LINES_TO_TRIM:
            break
        return lines

    if start == 0:
        return lines
    prefix = lines[:start]
    if start >= _MIN_TOC_LINES_TO_TRIM:
        return lines[start:]
    if any(line_looks_like_nav_blob(ln) for ln in prefix):
        return lines[start:]
    if start >= 2:
        return lines[start:]
    return lines


def extraction_quality_score(lines: list[str]) -> float:
    if not lines:
        return 0.0
    body = "\n".join(lines)
    if len(body) < 40:
        return 0.1

    total = len(lines)
    para_lines = sum(1 for ln in lines if line_looks_like_body_paragraph(ln))
    nav_lines = sum(
        1 for ln in lines if line_looks_like_toc_entry(ln) or line_looks_like_nav_blob(ln)
    )
    nav_ratio = nav_lines / total
    para_ratio = para_lines / total
    avg_len = len(body) / total
    score = min(2.0, para_ratio * 2.5) + min(1.0, avg_len / 100.0) - min(2.0, nav_ratio * 3.0)
    if len(body) >= 500 and para_ratio >= 0.2:
        score += 0.3
    return score


def normalize_extracted_lines(lines: list[str]) -> list[str]:
    lines = merge_broken_lines_stable(lines)
    lines = collapse_adjacent_duplicate_lines(lines)
    lines = trim_leading_toc_block(lines)
    lines = drop_leading_orphan_category(lines)
    lines = drop_header_zone_duplicate_title(lines)
    lines = apply_conservative_tail_trim(lines)
    lines = trim_trailing_header_echo(lines)
    return collapse_adjacent_duplicate_lines(lines)


def line_matches_tail_marker(line: str) -> bool:
    text = (line or "").strip()
    if not text or len(text) > 120:
        return False
    lower = text.lower()
    for marker in _HIGH_CONFIDENCE_TAIL_MARKERS:
        marker_lower = marker.lower()
        if text == marker or text.startswith(marker):
            return True
        if marker_lower in lower and len(text) <= len(marker) + 48:
            return True
    return False


def apply_conservative_tail_trim(lines: list[str]) -> list[str]:
    if not lines:
        return lines
    body = "\n".join(lines)
    if len(body) < _MIN_CHARS_FOR_TAIL_TRIM:
        return lines

    min_chars_before = int(len(body) * _TAIL_TRIM_MIN_BODY_RATIO)
    char_count = 0
    min_start_idx = len(lines)
    for i, ln in enumerate(lines):
        char_count += len(ln) + 1
        if char_count >= min_chars_before:
            min_start_idx = i + 1
            break

    for i in range(min_start_idx, len(lines)):
        if line_matches_tail_marker(lines[i]):
            return lines[:i]
    return lines


def drop_noise_tags(root) -> None:
    for tag in root.select(_NOISE_TAG_SELECTORS):
        tag.decompose()


def drop_page_level_noise(soup) -> None:
    for tag in soup.select(_PAGE_LEVEL_NOISE_SELECTORS):
        tag.decompose()


def _is_dom_descendant(ancestor, node) -> bool:
    parent = getattr(node, "parent", None)
    while parent is not None:
        if parent is ancestor:
            return True
        parent = getattr(parent, "parent", None)
    return False


def _score_content_node(node) -> float:
    text = node.get_text(separator="\n", strip=True)
    if not text:
        return -1.0

    paragraphs = node.find_all("p")
    paragraph_len = sum(len(p.get_text(strip=True)) for p in paragraphs)
    link_len = sum(len(a.get_text(strip=True)) for a in node.find_all("a"))
    text_len = max(len(text), 1)
    paragraph_ratio = paragraph_len / text_len
    link_ratio = link_len / text_len

    score = len(text) * (0.35 + 0.65 * min(1.0, paragraph_ratio * 2.0))
    score *= 1.0 - min(0.85, link_ratio * 1.2)
    if node.name in {"article", "main"}:
        score *= 1.15
    class_tokens = " ".join(node.get("class") or []).lower()
    if any(token in class_tokens for token in ("content", "article", "markdown", "doc", "post")):
        score *= 1.1
    if any(token in class_tokens for token in ("sidebar", "nav", "menu", "toc")):
        score *= 0.35
    return score


def _collect_container_candidates(soup) -> list:
    candidates: list = []
    seen: set[int] = set()

    def add(node) -> None:
        node_id = id(node)
        if node_id in seen:
            return
        seen.add(node_id)
        candidates.append(node)

    for selector in _CONTENT_CONTAINER_SELECTORS:
        for node in soup.select(selector):
            add(node)
    for node in soup.find_all(["article", "main", "section", "div"]):
        add(node)
    return candidates


def _prune_dominated_parents(candidates: list) -> list:
    scored = [(node, _score_content_node(node)) for node in candidates]
    kept: list = []
    for node, score in scored:
        if score < 0:
            continue
        dominated = False
        for other, other_score in scored:
            if other is node or other_score < 0:
                continue
            if _is_dom_descendant(node, other) and other_score >= score * 0.85:
                dominated = True
                break
        if not dominated:
            kept.append(node)
    return kept or [node for node, score in scored if score >= 0]


def pick_content_container(soup):
    candidates = _prune_dominated_parents(_collect_container_candidates(soup))
    best = None
    best_score = -1.0
    for node in candidates:
        score = _score_content_node(node)
        if score > best_score:
            best = node
            best_score = score
    return best or soup.body or soup


def clean_lines_from_text(text: str) -> list[str]:
    lines = [ln.strip() for ln in text.splitlines() if not line_is_generic_chrome(ln)]
    return normalize_extracted_lines(lines)


def _lines_from_soup(soup) -> list[str]:
    drop_page_level_noise(soup)
    preferred = pick_content_container(soup)
    drop_noise_tags(preferred)
    lines = clean_lines_from_text(preferred.get_text(separator="\n", strip=True))
    if lines:
        return lines
    for tag in soup(["nav", "header", "footer", "aside"]):
        tag.decompose()
    return clean_lines_from_text(soup.get_text(separator="\n", strip=True))


def _quality_is_poor(lines: list[str]) -> bool:
    if not lines:
        return True
    body = "\n".join(lines)
    if len(body) < _MIN_QUALITY_BODY_CHARS:
        return True
    score = extraction_quality_score(lines)
    if score < _QUALITY_FALLBACK_THRESHOLD:
        return True
    nav_lines = sum(
        1 for ln in lines if line_looks_like_toc_entry(ln) or line_looks_like_nav_blob(ln)
    )
    return len(lines) > 15 and nav_lines / len(lines) > 0.5


def _try_trafilatura_fallback(html: str, url: str) -> list[str]:
    try:
        from tools.web.common import extract_with_trafilatura
    except Exception as e:  # noqa: BLE001
        logger.debug("static_body_extract trafilatura import skipped: %s", e)
        return []

    try:
        extracted = extract_with_trafilatura(html, url or "")
    except Exception as e:  # noqa: BLE001
        logger.debug("static_body_extract trafilatura fallback failed: %s", e)
        return []

    if not extracted:
        return []
    lines = [
        ln.strip()
        for ln in extracted.splitlines()
        if ln.strip() and not line_is_generic_chrome(ln)
    ]
    return normalize_extracted_lines(lines)


def minimal_html_to_plain_text(html: str, *, url: str = "") -> str:
    """正文优先清洗：容器评分 → 噪音删除 → TOC 裁剪 → 保守尾部裁剪 → 单次 trafilatura 回退。"""
    try:
        from bs4 import BeautifulSoup
    except Exception as e:  # noqa: BLE001
        logger.warning("static_body_extract BeautifulSoup missing: %s", e)
        return re.sub(r"\s+", " ", (html or "").strip())[:_MAX_PLAIN_CHARS]

    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup(["script", "style", "noscript", "iframe", "svg"]):
        tag.decompose()

    lines = _lines_from_soup(soup)
    primary_score = extraction_quality_score(lines)
    if _quality_is_poor(lines):
        fallback_lines = _try_trafilatura_fallback(html or "", url)
        if fallback_lines:
            fallback_score = extraction_quality_score(fallback_lines)
            if fallback_score > primary_score * 1.05 or (
                primary_score < _QUALITY_FALLBACK_THRESHOLD
                and fallback_score > primary_score
            ):
                logger.debug(
                    "static_body_extract trafilatura fallback selected score=%.2f primary=%.2f",
                    fallback_score,
                    primary_score,
                )
                lines = fallback_lines
    return "\n".join(lines)[:_MAX_PLAIN_CHARS]
