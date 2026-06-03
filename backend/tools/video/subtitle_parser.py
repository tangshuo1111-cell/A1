from __future__ import annotations

import re
from pathlib import Path

_SRT_TS = re.compile(
    r"(?P<start>\d{2}:\d{2}:\d{2}[,.]\d{3})\s*-->\s*(?P<end>\d{2}:\d{2}:\d{2}[,.]\d{3})"
)
_VTT_TS = re.compile(
    r"(?P<start>\d{2}:\d{2}:\d{2}\.\d{3})\s*-->\s*(?P<end>\d{2}:\d{2}:\d{2}\.\d{3})"
)


def _ts_to_seconds(value: str) -> float:
    raw = value.replace(",", ".")
    hh, mm, rest = raw.split(":")
    ss, ms = rest.split(".")
    return int(hh) * 3600 + int(mm) * 60 + int(ss) + int(ms) / 1000


def parse_subtitle_file(path: str | Path) -> tuple[list[dict[str, object]], str]:
    p = Path(path)
    text = p.read_text(encoding="utf-8", errors="replace")
    ext = p.suffix.lower()
    if ext == ".txt":
        cleaned = text.strip()
        return ([{"start_time": 0.0, "end_time": 0.0, "text": cleaned}] if cleaned else [], "txt")

    lines = [line.rstrip("\n\r") for line in text.splitlines()]
    segments: list[dict[str, object]] = []
    i = 0
    ts_re = _VTT_TS if ext == ".vtt" else _SRT_TS
    while i < len(lines):
        line = lines[i].strip()
        if not line or line.upper() == "WEBVTT" or line.isdigit():
            i += 1
            continue
        m = ts_re.match(line)
        if not m:
            raise ValueError(f"invalid subtitle timestamp: {line}")
        i += 1
        buffer: list[str] = []
        while i < len(lines) and lines[i].strip():
            buffer.append(lines[i].strip())
            i += 1
        body = "\n".join(buffer).strip()
        if body:
            segments.append(
                {
                    "start_time": _ts_to_seconds(m.group("start")),
                    "end_time": _ts_to_seconds(m.group("end")),
                    "text": body,
                }
            )
        i += 1
    return segments, ext.lstrip(".")


def subtitle_segments_to_text(segments: list[dict[str, object]]) -> str:
    return "\n".join(str(seg.get("text") or "").strip() for seg in segments if str(seg.get("text") or "").strip()).strip()

