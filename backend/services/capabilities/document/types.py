"""Document capability shared types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class EarlyDocumentOutcome:
    """文档 prepare 早期阶段产出（complex gather 并行 worker 使用）。"""

    pending_item_early: Any = None
    source_type: str = ""
    error_code: str = ""
