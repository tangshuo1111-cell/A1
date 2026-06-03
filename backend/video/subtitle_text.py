"""字幕文本解析与清洗工具。"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_TIMECODE_RE = re.compile(
    r"^\d+\s*$|^\d{1,2}:\d{2}:\d{2}[,\.]\d{1,3}\s*-->\s*\d{1,2}:\d{2}:\d{2}[,\.]\d{1,3}.*$",
    re.MULTILINE,
)
_VTT_HEADER_RE = re.compile(r"^WEBVTT.*$|^Kind:.*$|^Language:.*$", re.MULTILINE)
_VTT_CUE_SETTINGS_RE = re.compile(
    r"^\s*(?:align|line|position|size|vertical|region):\S+(?:\s+(?:align|line|position|size|vertical|region):\S+)*\s*$",
    re.MULTILINE,
)
_TAG_RE = re.compile(r"<[^>]+>")

_ROLLING_OVERLAP_MIN_CHARS = 4


def _drop_rolling_overlap(blocks: list[str]) -> list[str]:
    """去掉 YouTube 自动翻译字幕的滚动重复。"""
    out: list[str] = []
    prev = ""
    for cur in blocks:
        if not cur:
            continue
        if prev and cur == prev:
            continue
        if prev and cur.startswith(prev) and len(cur) > len(prev):
            cur = cur[len(prev):].strip()
            if not cur:
                continue
        elif prev:
            max_overlap = min(len(prev), len(cur))
            chosen = 0
            for k in range(max_overlap, _ROLLING_OVERLAP_MIN_CHARS - 1, -1):
                if prev.endswith(cur[:k]):
                    chosen = k
                    break
            if chosen:
                cur = cur[chosen:].strip()
                if not cur:
                    continue
        out.append(cur)
        prev = cur
    return out


def _strip_subtitle_markup(text: str) -> str:
    """把 .srt / .vtt 字幕清成纯文本段落。"""
    if not text:
        return ""
    s = _VTT_HEADER_RE.sub("", text)
    s = _TIMECODE_RE.sub("", s)
    s = _VTT_CUE_SETTINGS_RE.sub("", s)
    s = _TAG_RE.sub("", s)
    blocks: list[str] = []
    for block in re.split(r"\n\s*\n+", s):
        clean = " ".join(line.strip() for line in block.splitlines() if line.strip())
        if clean:
            blocks.append(clean)
    blocks = _drop_rolling_overlap(blocks)
    return "\n".join(blocks).strip()


def _read_subtitle_text_from_files(
    info: dict[str, Any], workdir: Path
) -> tuple[str, str]:
    """从 info dict 里挖出已下载的字幕文件，读为纯文本。

    返回 (text, lang)；找不到则返回 ("", "")。
    """
    requested = info.get("requested_subtitles") or {}
    for lang, sub_info in requested.items():
        if not isinstance(sub_info, dict):
            continue
        fp = sub_info.get("filepath") or ""
        if not fp:
            continue
        p = Path(fp)
        if not p.exists():
            for cand in workdir.glob(f"*.{lang}.*"):
                if cand.is_file():
                    p = cand
                    break
        if p.exists():
            try:
                raw = p.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            return _strip_subtitle_markup(raw), str(lang)
    return "", ""
