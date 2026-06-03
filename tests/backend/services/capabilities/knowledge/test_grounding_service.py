from __future__ import annotations

from rag.schema import RetrievedChunk
from services.capabilities.knowledge.grounding_service import chunks_to_compact_prompt_block


def _chunk(idx: int, text: str, *, title: str = "Doc") -> RetrievedChunk:
    return RetrievedChunk(
        source_id=f"s{idx}",
        chunk_id=f"s{idx}::chunk::{idx}",
        text=text,
        metadata={"title": title, "chunk_index": idx},
    )


def test_compact_prompt_block_prefers_text_over_verbose_ids() -> None:
    block = chunks_to_compact_prompt_block(
        [
            _chunk(1, "第一段正文" * 20, title="A"),
            _chunk(2, "第二段正文" * 20, title="B"),
            _chunk(3, "第三段正文" * 20, title="C"),
            _chunk(4, "第四段正文" * 20, title="D"),
        ],
        max_chunks=3,
        max_chars=220,
    )
    assert "材料1（A）" in block
    assert "chunk::" not in block
    assert "s1" not in block
    assert "第四段正文" not in block
    assert len(block) <= 220


def test_compact_prompt_block_default_is_more_aggressive() -> None:
    block = chunks_to_compact_prompt_block(
        [
            _chunk(1, "第一段正文" * 80, title="A"),
            _chunk(2, "第二段正文" * 80, title="B"),
            _chunk(3, "第三段正文" * 80, title="C"),
        ],
    )
    assert "材料1（A）" in block
    assert "材料2（B）" in block
    assert "材料3（C）" not in block
    assert len(block) <= 900
