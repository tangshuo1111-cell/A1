"""Build critic_check for both multisource and default chains."""

from __future__ import annotations

import uuid
from typing import Any


def build_critic_check(
    job: dict[str, Any],
    comparison_matrix: dict[str, Any] | None,
    source_briefs: list[dict[str, Any]],
) -> dict[str, Any]:
    comparison_matrix = comparison_matrix or {}
    brief_map = {brief.get("source_brief_id", ""): brief for brief in source_briefs}
    unsupported_claims: list[dict[str, Any]] = []
    weak_evidence_claims: list[dict[str, Any]] = []
    evidence_mismatch: list[dict[str, Any]] = []
    missing_evidence: list[dict[str, Any]] = []
    conflict_without_resolution: list[dict[str, Any]] = []
    limitations: list[str] = []

    evidence_links = list(comparison_matrix.get("evidence_links") or [])
    if comparison_matrix and not evidence_links:
        unsupported_claims.append(
            {
                "claim": comparison_matrix.get("summary", "comparison_summary"),
                "reason": "comparison_matrix 没有 evidence_links 支撑",
                "severity": "high",
                "suggested_action": "remove_from_final_answer",
            }
        )

    linked_brief_ids = {link.get("source_brief_id", "") for link in evidence_links}
    for brief in source_briefs:
        bid = brief.get("source_brief_id", "")
        spans = list(brief.get("evidence_spans") or [])
        if not spans:
            missing_evidence.append(
                {
                    "claim": "；".join((brief.get("key_points") or [])[:2]) or brief.get("title", ""),
                    "source_brief_id": bid,
                    "reason": "source_brief 缺少 evidence_spans",
                }
            )
        elif brief.get("quality") == "low" or len(spans) == 1:
            weak_evidence_claims.append(
                {
                    "claim": "；".join((brief.get("key_points") or [])[:2]) or brief.get("title", ""),
                    "reason": "证据片段过少或质量较低",
                    "related_source_id": brief.get("source_id", ""),
                    "related_chunk_id": spans[0].get("chunk_id", ""),
                    "severity": "medium",
                    "suggested_action": "state_limitation_or_request_feedback",
                }
            )
        if comparison_matrix and bid not in linked_brief_ids:
            evidence_mismatch.append(
                {
                    "claim": brief.get("title", ""),
                    "reason": "comparison_matrix 未引用该 source_brief 的证据",
                    "related_source_brief_id": bid,
                }
            )

    for conflict in comparison_matrix.get("conflicts") or []:
        source_brief_ids = [sid for sid in conflict.get("source_brief_ids", []) if sid]
        if len(source_brief_ids) < 2:
            conflict_without_resolution.append(
                {
                    "claim": conflict.get("claim", ""),
                    "reason": "冲突项缺少双侧来源锚点",
                }
            )
            continue
        for source_brief_id in source_brief_ids:
            if source_brief_id not in brief_map:
                evidence_mismatch.append(
                    {
                        "claim": conflict.get("claim", ""),
                        "reason": "conflict 引用了不存在的 source_brief",
                        "related_source_brief_id": source_brief_id,
                    }
                )

    if not source_briefs:
        limitations.append("没有成功来源，无法形成可回答的比较结论。")
    elif weak_evidence_claims:
        limitations.append("存在弱证据来源，最终回答必须显式说明不确定性。")

    revision_required = bool(unsupported_claims or missing_evidence or conflict_without_resolution)
    safe_to_answer = bool(source_briefs) and not unsupported_claims
    return {
        "critic_check_id": f"critic_{uuid.uuid4().hex[:10]}",
        "job_id": job.get("job_id", ""),
        "comparison_id": comparison_matrix.get("comparison_id", ""),
        "unsupported_claims": unsupported_claims,
        "weak_evidence_claims": weak_evidence_claims,
        "evidence_mismatch": evidence_mismatch,
        "missing_evidence": missing_evidence,
        "conflict_without_resolution": conflict_without_resolution,
        "revision_required": revision_required,
        "safe_to_answer": safe_to_answer,
        "limitations": limitations,
    }


def build_default_chain_critic_check(
    *,
    material_sufficiency: str,
    evidence_envelopes: list[Any],
    failures: list[dict[str, Any]],
    force_skip_evidence: bool = False,
) -> dict[str, Any]:
    unsupported_claims: list[dict[str, Any]] = []
    weak_evidence_claims: list[dict[str, Any]] = []
    evidence_mismatch: list[dict[str, Any]] = []
    missing_evidence: list[dict[str, Any]] = []
    conflict_without_resolution: list[dict[str, Any]] = []
    limitations: list[str] = []

    envs = list(evidence_envelopes or [])
    successful = [env for env in envs if getattr(env, "status", "") == "success" and getattr(env, "text", "")]
    failed = [env for env in envs if getattr(env, "status", "") == "failed"]
    pending = [env for env in envs if getattr(env, "status", "") == "pending"]

    if force_skip_evidence:
        limitations.append("本轮按直答快路径处理，未要求事实性证据。")
    elif material_sufficiency in {"no_match", "insufficient"} and not successful:
        missing_evidence.append(
            {
                "claim": "current_answer_basis",
                "reason": "没有成功证据来源支撑当前回答",
            }
        )
        limitations.append("当前没有成功证据来源，最终回答必须保守说明。")
    elif material_sufficiency == "low_confidence":
        weak_evidence_claims.append(
            {
                "claim": "knowledge_block",
                "reason": "知识证据相关性偏低",
                "severity": "medium",
                "suggested_action": "state_limitation_or_request_feedback",
            }
        )
        limitations.append("检索证据相关性偏低，最终回答必须显式说明不确定性。")

    for env in failed:
        error_code = str(getattr(env, "error_code", "") or "")
        if error_code:
            limitations.append(f"{getattr(env, 'source_type', 'source')} 失败：{error_code}")
    for env in pending:
        limitations.append(f"{getattr(env, 'source_type', 'source')} 仍在后台处理中，当前结论不完整。")
    for failure in failures or []:
        tool = str(failure.get("tool", "") or "tool")
        reason = str(failure.get("reason", "") or "failed")
        limitations.append(f"{tool} 失败：{reason}")

    limitations = list(dict.fromkeys(limitations))
    revision_required = bool(missing_evidence or weak_evidence_claims or failed)
    safe_to_answer = force_skip_evidence or material_sufficiency == "sufficient"
    return {
        "critic_check_id": f"critic_{uuid.uuid4().hex[:10]}",
        "job_id": "",
        "comparison_id": "",
        "unsupported_claims": unsupported_claims,
        "weak_evidence_claims": weak_evidence_claims,
        "evidence_mismatch": evidence_mismatch,
        "missing_evidence": missing_evidence,
        "conflict_without_resolution": conflict_without_resolution,
        "revision_required": revision_required,
        "safe_to_answer": safe_to_answer,
        "limitations": limitations,
    }
