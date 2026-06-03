"""Evidence grounding — chunk context assembly and RAG marker cleanup."""

from __future__ import annotations

from typing import Any


def chunks_to_context_block(chunks: list[Any], *, separator: str = "\n\n---\n\n") -> str:
    lines: list[str] = []
    for chunk in chunks:
        if hasattr(chunk, "to_context_line"):
            lines.append(chunk.to_context_line())
            continue
        text = getattr(chunk, "text", None)
        if text is None and isinstance(chunk, dict):
            text = chunk.get("text") or chunk.get("content")
        lines.append(str(text or chunk).strip())
    return separator.join(line for line in lines if line)


def chunks_to_compact_prompt_block(
    chunks: list[Any],
    *,
    max_chunks: int = 2,
    max_chars: int = 900,
) -> str:
    """Build a compact evidence block for answer prompts.

    Prefer正文 over verbose source_id/chunk_id labels to reduce token load while
    preserving multiple evidence points for synthesis.
    """
    parts: list[str] = []
    remaining = max(0, int(max_chars))
    for idx, chunk in enumerate(list(chunks)[: max(0, int(max_chunks))], start=1):
        text = getattr(chunk, "text", None)
        if text is None and isinstance(chunk, dict):
            text = chunk.get("text") or chunk.get("content")
        body = strip_rag_internal_markers(str(text or "").strip())
        if not body:
            continue
        title = ""
        metadata = getattr(chunk, "metadata", None)
        if isinstance(metadata, dict):
            title = str(metadata.get("title") or "").strip()
        short_title = title[:18] if title else ""
        header = f"材料{idx}"
        if short_title:
            header += f"（{short_title}）"
        header += "："
        body = " ".join(body.split())
        piece = f"{header}{body}"
        if len(piece) > remaining:
            piece = piece[:remaining].rstrip()
        if not piece:
            break
        parts.append(piece)
        remaining -= len(piece) + 2
        if remaining <= 0:
            break
    return "\n\n".join(parts)


def is_rag_boost_header(text: str) -> bool:
    from rag.result_cleaner import is_rag_boost_header as _is_boost

    return _is_boost(text)


def strip_rag_internal_markers(text: str) -> str:
    from rag.result_cleaner import strip_rag_internal_markers as _strip

    return _strip(text)


def sort_hits_body_before_boost(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from rag.result_cleaner import sort_hits_body_before_boost as _sort

    return _sort(rows)
