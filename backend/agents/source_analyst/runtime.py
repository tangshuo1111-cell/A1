"""Middle source brief builder for a single source.

This module stays on the old import path for compatibility only.
It is an internal Middle-stage helper, not a fourth Agent runtime.
"""

from __future__ import annotations

import re
import uuid
from typing import Any


class SourceAnalystRuntime:
    """Rule-based single-source brief builder used inside MiddleAgentRuntime."""

    def analyze(self, source_task: dict[str, Any], chunks: list[dict[str, Any]]) -> dict[str, Any]:
        text = "\n".join(str(c.get("text", "")) for c in chunks).strip()
        title = str(source_task.get("metadata", {}).get("title") or source_task.get("raw_input") or "source")
        sentences = [s.strip() for s in re.split(r"(?<=[。！？.!?])\s+|\n+", text) if s.strip()]
        key = sentences[:3] or ([text[:240]] if text else [])
        words = re.findall(r"[\w\u4e00-\u9fff]+", text)
        quality = "good" if len(words) >= 80 else "medium" if len(words) >= 25 else "low"
        evidence = []
        for c in chunks[:3]:
            excerpt = str(c.get("text", ""))[:280]
            if excerpt:
                evidence.append(
                    {
                        "chunk_id": c.get("chunk_id", ""),
                        "source_id": c.get("source_id", ""),
                        "text_excerpt": excerpt,
                        "start_offset": 0,
                        "end_offset": len(excerpt),
                        "score": c.get("score", 1.0),
                    }
                )
        angle = "以事实陈述和论点展开为主"
        lower = text.lower()
        if any(x in lower for x in ("benefit", "advantage", "优点", "价值")):
            angle = "偏向阐述价值与优点"
        if any(x in lower for x in ("risk", "limitation", "局限", "问题")):
            angle = "同时关注风险或局限"
        return {
            "source_brief_id": f"srcbrief_{uuid.uuid4().hex[:10]}",
            "source_task_id": source_task.get("source_task_id", ""),
            "source_id": source_task.get("source_id", ""),
            "title": title,
            "source_type": source_task.get("input_type", "web_url"),
            "status": "succeeded" if evidence else "partial",
            "main_claims": key[:2] or ["该来源未提取到足够长的主张。"],
            "key_points": key or ["正文内容过短，无法提取更多要点。"],
            "strengths": ["提供了可追溯的来源正文片段。"] if evidence else [],
            "weaknesses": ["单来源摘要未做跨来源比较。"],
            "angle": angle,
            "evidence_spans": evidence,
            "quality": quality,
            "limitations": ["当前阶段只负责单来源摘要；跨来源比较由 MiddleAgentRuntime 后续统一生成。"],
            "metadata": {"chunk_count": len(chunks), "raw_input": source_task.get("raw_input", "")},
        }
