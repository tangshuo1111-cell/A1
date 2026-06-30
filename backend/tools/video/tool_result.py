from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from tools.document.tool_result import DocumentToolResult


@dataclass
class VideoToolResult(DocumentToolResult):
    source_ref: str = ""
    title: str = ""
    transcript_source: str = ""
    subtitle_format: str = ""
    segments: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.metadata.setdefault("title", self.title)
        self.metadata.setdefault("transcript_source", self.transcript_source)
        self.metadata.setdefault("subtitle_format", self.subtitle_format)
        self.metadata.setdefault("source_ref", self.source_ref)
        if self.segments and "segments" not in self.structured_data:
            self.structured_data["segments"] = self.segments

