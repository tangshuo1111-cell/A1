"""Permanent metrics diagnostic helpers (product metrics line — read-only)."""

from __future__ import annotations

from typing import Any

from application.chat.refine_kind import (
    build_complex_failure_breakdown,
    enrich_metrics_diagnostic_row,
)

__all__ = [
    "build_complex_failure_breakdown",
    "enrich_metrics_diagnostic_row",
    "render_diagnostic_summary_lines",
]


def render_diagnostic_summary_lines(breakdown: dict[str, Any]) -> list[str]:
    lines = [
        f"complex_total={breakdown.get('complex_total', 0)}",
        f"complex_partial={breakdown.get('complex_partial', 0)}",
    ]
    buckets = breakdown.get("partial_buckets") or {}
    if buckets:
        parts = ", ".join(f"{k}:{v}" for k, v in sorted(buckets.items()))
        lines.append(f"partial_buckets={parts}")
    flip = breakdown.get("would_answer_refine_ids") or []
    if flip:
        lines.append(f"would_answer_refine={','.join(str(x) for x in flip)}")
    return lines
