"""Build comparison_matrix from source_briefs inside Middle runtime."""

from __future__ import annotations

import re
import uuid
from collections import Counter
from typing import Any

_TOKEN_RE = re.compile(r"[\w\u4e00-\u9fff]+")
_STOPWORDS = {
    "the",
    "and",
    "that",
    "with",
    "this",
    "from",
    "have",
    "their",
    "what",
    "which",
    "about",
    "into",
    "一个",
    "一些",
    "这个",
    "这些",
    "以及",
    "主要",
    "分别",
    "进行",
}


def _tokenize(text: str) -> set[str]:
    return {
        token.lower()
        for token in _TOKEN_RE.findall(text or "")
        if len(token) >= 2 and token.lower() not in _STOPWORDS
    }


def _claim_link(brief: dict[str, Any], claim: str) -> dict[str, Any]:
    span: dict[str, Any] = next(iter(brief.get("evidence_spans") or []), {})
    return {
        "source_brief_id": brief.get("source_brief_id", ""),
        "source_id": brief.get("source_id", ""),
        "chunk_id": span.get("chunk_id", ""),
        "text_excerpt": span.get("text_excerpt", ""),
        "claim": claim,
    }


def build_comparison_matrix(job: dict[str, Any], source_briefs: list[dict[str, Any]]) -> dict[str, Any]:
    comparison_id = f"cmp_{uuid.uuid4().hex[:10]}"
    source_brief_ids = [brief.get("source_brief_id", "") for brief in source_briefs]

    point_rows: list[tuple[dict[str, Any], str, set[str]]] = []
    for brief in source_briefs:
        for point in (brief.get("key_points") or [])[:3]:
            point_rows.append((brief, str(point), _tokenize(str(point))))

    common_points: list[str] = []
    evidence_links: list[dict[str, Any]] = []
    common_keys: set[str] = set()
    for idx, (brief_a, point_a, tok_a) in enumerate(point_rows):
        if not tok_a:
            continue
        for brief_b, point_b, tok_b in point_rows[idx + 1 :]:
            if brief_a.get("source_brief_id") == brief_b.get("source_brief_id"):
                continue
            overlap = sorted(tok_a & tok_b)
            if len(overlap) < 2:
                continue
            key = "|".join(overlap[:4])
            if key in common_keys:
                continue
            common_keys.add(key)
            common_points.append(f"多个来源都提到：{' / '.join(overlap[:4])}")
            evidence_links.append(_claim_link(brief_a, point_a))
            evidence_links.append(_claim_link(brief_b, point_b))

    per_brief_tokens = {
        brief.get("source_brief_id", ""): _tokenize(" ".join((brief.get("key_points") or [])[:3]))
        for brief in source_briefs
    }
    token_counts = Counter(token for tokens in per_brief_tokens.values() for token in tokens)

    different_points: list[dict[str, Any]] = []
    angle_differences: list[dict[str, Any]] = []
    strength_comparison: list[dict[str, Any]] = []
    weakness_comparison: list[dict[str, Any]] = []
    source_limitations: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    positive_markers = ("advantage", "benefit", "improve", "优点", "价值", "效率")
    negative_markers = ("risk", "limitation", "problem", "局限", "风险", "缓慢")

    for brief in source_briefs:
        bid = brief.get("source_brief_id", "")
        tokens = per_brief_tokens.get(bid, set())
        unique_terms = sorted(token for token in tokens if token_counts[token] == 1)[:4]
        different_points.append(
            {
                "source_brief_id": bid,
                "source_id": brief.get("source_id", ""),
                "point": "；".join((brief.get("key_points") or [])[:2]) or "未提取到稳定差异点",
                "unique_terms": unique_terms,
            }
        )
        angle_differences.append(
            {
                "source_brief_id": bid,
                "source_id": brief.get("source_id", ""),
                "angle": brief.get("angle", ""),
            }
        )
        strength_comparison.append(
            {
                "source_brief_id": bid,
                "source_id": brief.get("source_id", ""),
                "strengths": list(brief.get("strengths") or []),
            }
        )
        weakness_comparison.append(
            {
                "source_brief_id": bid,
                "source_id": brief.get("source_id", ""),
                "weaknesses": list(brief.get("weaknesses") or []),
            }
        )
        source_limitations.append(
            {
                "source_brief_id": bid,
                "source_id": brief.get("source_id", ""),
                "limitations": list(brief.get("limitations") or []),
                "quality": brief.get("quality", ""),
            }
        )

    positive_briefs = [
        brief for brief in source_briefs
        if any(marker in " ".join(brief.get("key_points") or []).lower() for marker in positive_markers)
    ]
    negative_briefs = [
        brief for brief in source_briefs
        if any(marker in " ".join(brief.get("key_points") or []).lower() for marker in negative_markers)
    ]
    if positive_briefs and negative_briefs:
        pos = positive_briefs[0]
        neg = negative_briefs[0]
        conflicts.append(
            {
                "claim": "来源对价值与风险的强调存在明显差异",
                "source_brief_ids": [pos.get("source_brief_id", ""), neg.get("source_brief_id", "")],
            }
        )
        evidence_links.append(_claim_link(pos, (pos.get("key_points") or [""])[0]))
        evidence_links.append(_claim_link(neg, (neg.get("key_points") or [""])[0]))

    summary_bits = []
    if common_points:
        summary_bits.append(f"共同点 {len(common_points)} 项")
    if different_points:
        summary_bits.append(f"差异点 {len(different_points)} 项")
    if conflicts:
        summary_bits.append(f"冲突 {len(conflicts)} 项")

    return {
        "comparison_id": comparison_id,
        "job_id": job.get("job_id", ""),
        "source_brief_ids": source_brief_ids,
        "common_points": common_points,
        "different_points": different_points,
        "conflicts": conflicts,
        "angle_differences": angle_differences,
        "strength_comparison": strength_comparison,
        "weakness_comparison": weakness_comparison,
        "source_limitations": source_limitations,
        "evidence_links": evidence_links,
        "summary": "，".join(summary_bits) if summary_bits else "资料不足，尚未形成稳定比较矩阵",
        "status": "ready" if source_briefs else "insufficient",
    }
