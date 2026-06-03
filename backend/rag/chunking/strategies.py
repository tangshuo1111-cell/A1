"""Text chunking strategies (default: paragraph + max length)."""

from __future__ import annotations


def paragraph_700(text: str, max_len: int = 700) -> list[str]:
    """按段落与长度切块（与 legacy ingest._chunk_text 行为一致）。"""
    text = text.strip()
    if not text:
        return []
    chunks: list[str] = []
    buf: list[str] = []
    size = 0
    for para in text.split("\n\n"):
        p = para.strip()
        if not p:
            continue
        add = len(p) + (1 if buf else 0)
        if size + add > max_len and buf:
            chunks.append("\n".join(buf))
            buf = [p]
            size = len(p)
        else:
            buf.append(p)
            size += add
    if buf:
        chunks.append("\n".join(buf))
    out: list[str] = []
    for c in chunks:
        if len(c) <= max_len:
            out.append(c)
            continue
        for i in range(0, len(c), max_len):
            piece = c[i : i + max_len].strip()
            if piece:
                out.append(piece)
    return out
