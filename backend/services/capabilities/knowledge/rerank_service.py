"""KB rerank orchestration — score-based reorder before grounding."""

from __future__ import annotations

from typing import Any


def rerank_chunks(chunks: list[Any], *, top_k: int | None = None) -> list[Any]:
    if not chunks:
        return []
    ranked = sorted(
        chunks,
        key=lambda chunk: float(
            getattr(chunk, "combined_score", None)
            or getattr(chunk, "score_normalized", None)
            or getattr(chunk, "score", 0.0)
            or 0.0
        ),
        reverse=True,
    )
    if top_k is None:
        return ranked
    return ranked[: max(0, int(top_k))]
