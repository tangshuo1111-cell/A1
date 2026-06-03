from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VideoBackgroundTaskPayload:
    task_id: str
    source_type: str
    source_ref: str
    session_id: str
    artifact_ref: str | None = None
