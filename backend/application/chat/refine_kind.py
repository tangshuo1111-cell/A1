"""RefineKind — single contract for complex round-1 refine (material vs answer-only)."""

from __future__ import annotations

from typing import Any, Literal

from config.feature_flags import complex_refine_v2_active

RefineKind = Literal["none", "material", "answer_only"]

# Depth/structure failures — answer-only refine eligible (not material / honesty).
DEPTH_STRUCTURE_REASON_CODES: frozenset[str] = frozenset(
    {
        "answer_too_shallow",
        "complex_answer_not_deep_enough",
        "deep_complex_requires_agent",
        "case_analysis_missing",
        "decision_not_made",
        "structure_not_satisfied",
        "comparison_not_performed",
    }
)

MATERIAL_REASON_CODES: frozenset[str] = frozenset(
    {
        "kb_insufficient",
        "evidence_not_used",
        "material_insufficient",
    }
)

INTEGRITY_REASON_CODES: frozenset[str] = frozenset(
    {
        "answer_truncated",
        "answer_tail_incomplete",
        "answer_empty",
        "limitations_present",
    }
)

PartialBucket = Literal[
    "none",
    "misjudged_gate",
    "answer_only_gap",
    "material_gap",
    "commit_misroute",
    "insufficiency_expected",
    "budget_limited",
    "other",
]

_COMMIT_MARKERS = ("no_pending_found", "pending_commit", "保存资料时失败")
_COMMIT_PENDING_KINDS = frozenset({"pending_commit", "approval_blocked", "material_pending"})
_MATERIAL_LIMITATION_MARKERS = (
    "材料不足",
    "知识库",
    "网页证据",
    "未获得可用",
    "检索到可用片段",
    "无法基于材料",
    "仍缺少哪些证据",
    "现有材料不足",
    "未从知识库",
    "外部网页",
    "补网后仍未获得",
    "证据尚未补齐",
    "没有成功来源",
    "没有成功证据",
    "fetch_web",
    "web_fetch",
)


def _commit_blocked(*, pending_kind: str | None, answer_text: str) -> bool:
    pk = str(pending_kind or "").strip().lower()
    if pk in _COMMIT_PENDING_KINDS:
        return True
    text = str(answer_text or "")
    return any(marker in text for marker in _COMMIT_MARKERS)


def _material_relevant_chunks(
    *,
    retrieved_chunks_count: int,
    kb_evidence_tier: str = "",
) -> bool:
    """True when retrieved chunks should block general-lane material narrow."""
    if retrieved_chunks_count <= 0:
        return False
    tier_l = str(kb_evidence_tier or "").strip().lower()
    return tier_l not in {"weak", "none"}


def _effective_answer_only_codes(
    reason_codes: tuple[str, ...] | list[str],
    limitations: list[str],
    *,
    lane: str,
    use_knowledge: bool,
    retrieved_chunks_count: int,
    kb_evidence_tier: str = "",
) -> set[str]:
    codes = set(reason_codes or ())
    if not complex_refine_v2_active():
        return codes
    lane_l = str(lane or "").strip().lower()
    if lane_l == "kb" or use_knowledge or _material_relevant_chunks(
        retrieved_chunks_count=retrieved_chunks_count,
        kb_evidence_tier=kb_evidence_tier,
    ):
        return codes
    codes -= MATERIAL_REASON_CODES
    if "limitations_present" in codes and _limitations_are_material_scope_only(limitations):
        codes.discard("limitations_present")
    return codes


def _depth_refine_eligible_despite_insufficiency(
    *,
    insufficient_evidence: bool,
    reason_codes: tuple[str, ...] | list[str],
    limitations: list[str] | None,
    lane: str,
    use_knowledge: bool,
    retrieved_chunks_count: int,
    kb_evidence_tier: str = "",
) -> bool:
    """General-lane reasoning: material-level insuf must not block depth-only refine."""
    if not insufficient_evidence or not complex_refine_v2_active():
        return False
    lane_l = str(lane or "").strip().lower()
    if lane_l == "kb" or use_knowledge or _material_relevant_chunks(
        retrieved_chunks_count=retrieved_chunks_count,
        kb_evidence_tier=kb_evidence_tier,
    ):
        return False
    codes = _effective_answer_only_codes(
        reason_codes,
        list(limitations or ()),
        lane=lane,
        use_knowledge=use_knowledge,
        retrieved_chunks_count=retrieved_chunks_count,
        kb_evidence_tier=kb_evidence_tier,
    )
    if not codes or codes & MATERIAL_REASON_CODES:
        return False
    if codes & (INTEGRITY_REASON_CODES - {"limitations_present"}):
        return False
    return bool(codes & DEPTH_STRUCTURE_REASON_CODES)


def _answer_only_core(
    *,
    reason_codes: tuple[str, ...] | list[str],
    need_second_round: bool,
    need_more_material: bool,
    insufficient_evidence: bool,
    pending_kind: str | None,
    answer_text: str,
    limitations: list[str] | None = None,
    lane: str = "general",
    use_knowledge: bool = False,
    retrieved_chunks_count: int = 0,
    kb_evidence_tier: str = "",
) -> bool:
    if not need_second_round or need_more_material:
        return False
    if insufficient_evidence and not _depth_refine_eligible_despite_insufficiency(
        insufficient_evidence=insufficient_evidence,
        reason_codes=reason_codes,
        limitations=limitations,
        lane=lane,
        use_knowledge=use_knowledge,
        retrieved_chunks_count=retrieved_chunks_count,
        kb_evidence_tier=kb_evidence_tier,
    ):
        return False
    if _commit_blocked(pending_kind=pending_kind, answer_text=answer_text):
        return False
    codes = _effective_answer_only_codes(
        reason_codes,
        list(limitations or ()),
        lane=lane,
        use_knowledge=use_knowledge,
        retrieved_chunks_count=retrieved_chunks_count,
        kb_evidence_tier=kb_evidence_tier,
    )
    if not codes:
        return False
    if codes & (INTEGRITY_REASON_CODES - {"limitations_present"}):
        return False
    return bool(codes & DEPTH_STRUCTURE_REASON_CODES)


def _limitations_are_material_scope_only(limitations: list[str]) -> bool:
    if not limitations:
        return False
    for limitation in limitations:
        text = str(limitation or "").strip()
        if not text:
            continue
        if any(marker in text for marker in _MATERIAL_LIMITATION_MARKERS):
            continue
        return False
    return True


def narrow_general_reasoning_gate_reasons(
    reasons: list[str],
    limitations: list[str],
    *,
    lane: str,
    use_knowledge: bool,
    retrieved_chunks_count: int,
    kb_evidence_tier: str = "",
) -> list[str]:
    """RefineV2: drop material/kb false positives on general lane without KB scope."""
    if not complex_refine_v2_active():
        return reasons
    lane_l = str(lane or "").strip().lower()
    if lane_l == "kb" or use_knowledge or _material_relevant_chunks(
        retrieved_chunks_count=retrieved_chunks_count,
        kb_evidence_tier=kb_evidence_tier,
    ):
        return reasons
    out = [code for code in reasons if code not in MATERIAL_REASON_CODES]
    if "limitations_present" in out and _limitations_are_material_scope_only(limitations):
        out = [code for code in out if code != "limitations_present"]
    return out


def narrow_kb_insufficient_reasons(
    reasons: list[str],
    *,
    lane: str,
    use_knowledge: bool,
    retrieved_chunks_count: int,
    kb_evidence_tier: str = "",
) -> list[str]:
    """Drop kb_insufficient when general reasoning has no KB scope (false-positive narrow)."""
    return narrow_general_reasoning_gate_reasons(
        reasons,
        [],
        lane=lane,
        use_knowledge=use_knowledge,
        retrieved_chunks_count=retrieved_chunks_count,
        kb_evidence_tier=kb_evidence_tier,
    )


def would_answer_only_refine_apply(
    *,
    reason_codes: tuple[str, ...] | list[str],
    need_second_round: bool,
    need_more_material: bool,
    insufficient_evidence: bool,
    pending_kind: str | None,
    answer_text: str,
    live: bool = True,
    limitations: list[str] | None = None,
    lane: str = "general",
    use_knowledge: bool = False,
    retrieved_chunks_count: int = 0,
    kb_evidence_tier: str = "",
) -> bool:
    """Shared predicate for shadow (live=False) and live answer-only refine (live=True)."""
    if live and not complex_refine_v2_active():
        return False
    return _answer_only_core(
        reason_codes=reason_codes,
        need_second_round=need_second_round,
        need_more_material=need_more_material,
        insufficient_evidence=insufficient_evidence,
        pending_kind=pending_kind,
        answer_text=answer_text,
        limitations=limitations,
        lane=lane,
        use_knowledge=use_knowledge,
        retrieved_chunks_count=retrieved_chunks_count,
        kb_evidence_tier=kb_evidence_tier,
    )


def _limitations_only_general_refine(
    *,
    reason_codes: tuple[str, ...] | list[str],
    limitations: list[str] | None,
    lane: str,
    use_knowledge: bool,
    retrieved_chunks_count: int,
    kb_evidence_tier: str,
    need_second_round: bool,
    need_more_material: bool,
) -> bool:
    """General-lane: stale material honesty lines → depth regen, not web gather."""
    if not complex_refine_v2_active() or not need_second_round:
        return False
    raw = {str(c) for c in (reason_codes or ()) if str(c).strip()}
    if raw != {"limitations_present"}:
        return False
    lane_l = str(lane or "").strip().lower()
    if lane_l == "kb" or use_knowledge:
        return False
    if _material_relevant_chunks(
        retrieved_chunks_count=retrieved_chunks_count,
        kb_evidence_tier=kb_evidence_tier,
    ):
        return False
    return not (need_more_material and _limitations_are_material_scope_only(list(limitations or ())) is False)


def resolve_refine_kind(
    *,
    need_second_round: bool,
    need_more_material: bool,
    reason_codes: tuple[str, ...] | list[str],
    insufficient_evidence: bool,
    pending_kind: str | None,
    answer_text: str,
    limitations: list[str] | None = None,
    lane: str = "general",
    use_knowledge: bool = False,
    retrieved_chunks_count: int = 0,
    kb_evidence_tier: str = "",
) -> RefineKind:
    if not need_second_round:
        return "none"
    effective_codes = _effective_answer_only_codes(
        reason_codes,
        list(limitations or ()),
        lane=lane,
        use_knowledge=use_knowledge,
        retrieved_chunks_count=retrieved_chunks_count,
        kb_evidence_tier=kb_evidence_tier,
    )
    if _limitations_only_general_refine(
        reason_codes=reason_codes,
        limitations=limitations,
        lane=lane,
        use_knowledge=use_knowledge,
        retrieved_chunks_count=retrieved_chunks_count,
        kb_evidence_tier=kb_evidence_tier,
        need_second_round=need_second_round,
        need_more_material=need_more_material,
    ):
        return "answer_only"
    if need_more_material or bool(effective_codes & MATERIAL_REASON_CODES):
        return "material"
    if would_answer_only_refine_apply(
        reason_codes=reason_codes,
        need_second_round=need_second_round,
        need_more_material=need_more_material,
        insufficient_evidence=insufficient_evidence,
        pending_kind=pending_kind,
        answer_text=answer_text,
        limitations=limitations,
        lane=lane,
        use_knowledge=use_knowledge,
        retrieved_chunks_count=retrieved_chunks_count,
        kb_evidence_tier=kb_evidence_tier,
    ):
        return "answer_only"
    return "none"


def classify_partial_bucket(
    row: dict[str, Any],
    *,
    refine_kind: RefineKind | None = None,
) -> PartialBucket:
    status = str(row.get("task_status") or "").strip().lower()
    if status != "partial":
        return "none"
    failure = str(row.get("failure_reason_code") or "").strip().lower()
    insuf = bool(row.get("insufficient_evidence"))
    if insuf or failure == "insufficiency":
        return "insufficiency_expected"
    answer = str(row.get("answer_summary") or "")
    pending = row.get("pending_kind")
    if _commit_blocked(pending_kind=str(pending) if pending else None, answer_text=answer):
        return "commit_misroute"
    stop = str(row.get("stop_reason") or "").strip().lower()
    events = row.get("autonomy_events") or []
    event_stops = {
        str(ev.get("stop_reason") or "").strip().lower()
        for ev in events
        if isinstance(ev, dict)
    }
    budget_stops = {"budget_exhausted", "max_round_reached", "llm_calls_exhausted", "tool_calls_exhausted"}
    if stop in budget_stops or event_stops & budget_stops:
        return "budget_limited"
    codes = set(row.get("quality_gate_reason_codes") or [])
    chunks = int(row.get("v15_retrieved_chunks_count") or 0)
    use_kb = bool(row.get("use_knowledge"))
    if codes & MATERIAL_REASON_CODES or (use_kb and chunks <= 1):
        return "material_gap"
    rk = refine_kind or str(row.get("refine_kind") or "none")
    if rk == "answer_only" or _answer_only_core(
        reason_codes=tuple(codes),
        need_second_round=True,
        need_more_material=False,
        insufficient_evidence=insuf,
        pending_kind=str(pending) if pending else None,
        answer_text=answer,
    ):
        return "answer_only_gap"
    if codes & DEPTH_STRUCTURE_REASON_CODES:
        return "misjudged_gate"
    return "other"


def enrich_metrics_diagnostic_row(row: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    """Add permanent diagnostic fields (read-only; does not change product behavior)."""
    out = dict(row)
    qg_codes = list(extra.get("quality_gate.reason_codes") or extra.get("quality_gate_reason_codes") or [])
    out["quality_gate_reason_codes"] = qg_codes
    out["stop_reason"] = extra.get("stop_reason") or ""
    events = extra.get("autonomy_events") or []
    out["autonomy_events"] = events if isinstance(events, list) else []
    out["refine_kind"] = extra.get("refine_kind") or "none"
    out["metrics_would_answer_refine"] = bool(
        extra.get("metrics.would_answer_refine")
        if "metrics.would_answer_refine" in extra
        else would_answer_only_refine_apply(
            reason_codes=qg_codes,
            need_second_round=bool(extra.get("quality_gate.need_second_round")),
            need_more_material=bool(extra.get("quality_gate.need_more_material")),
            insufficient_evidence=bool(extra.get("insufficient_evidence")),
            pending_kind=str(extra.get("pending_kind") or "") or None,
            answer_text=str(extra.get("answer") or out.get("answer_summary") or ""),
            live=False,
        )
    )
    out["metrics_partial_bucket"] = classify_partial_bucket(out, refine_kind=out.get("refine_kind"))
    blockers: list[str] = []
    if not out.get("is_complex_task"):
        blockers.append("not_complex_task")
    if str(out.get("task_status") or "").lower() != "succeeded":
        blockers.append(f"task_status={out.get('task_status')}")
    if out.get("insufficient_evidence"):
        blockers.append("insufficient_evidence")
    if out.get("quality_gate_passed") is False:
        blockers.append("quality_gate_passed=false")
    out["metrics_north_star_blockers"] = blockers
    return out


def build_complex_failure_breakdown(rows: list[dict[str, Any]]) -> dict[str, Any]:
    complex_rows = [r for r in rows if r.get("is_complex_task")]
    partial_rows = [r for r in complex_rows if str(r.get("task_status") or "").lower() == "partial"]
    buckets: dict[str, int] = {}
    for row in partial_rows:
        bucket = str(row.get("metrics_partial_bucket") or "other")
        buckets[bucket] = buckets.get(bucket, 0) + 1
    would_flip = [
        r.get("id")
        for r in partial_rows
        if r.get("metrics_would_answer_refine")
    ]
    return {
        "complex_total": len(complex_rows),
        "complex_partial": len(partial_rows),
        "partial_buckets": buckets,
        "would_answer_refine_ids": would_flip,
    }


def _latest_answer_only_trace(bundle: Any) -> dict[str, Any] | None:
    events = list(getattr(bundle, "autonomy_events", None) or [])
    for ev in reversed(events):
        if not isinstance(ev, dict):
            continue
        if str(ev.get("requested_action") or "") == "answer_only_regenerate":
            return ev
        payload = ev.get("payload") or {}
        if isinstance(payload, dict) and payload.get("refine_kind") == "answer_only":
            return ev
    return None


def is_answer_only_refine_bundle(bundle: Any) -> bool:
    """True when complex feedback scheduled depth-only round-1 regeneration."""
    if not complex_refine_v2_active():
        return False
    return _latest_answer_only_trace(bundle) is not None


def answer_only_refine_reason_codes(bundle: Any) -> tuple[str, ...]:
    ev = _latest_answer_only_trace(bundle)
    if not ev:
        return ()
    payload = ev.get("payload") or {}
    raw = payload.get("refine_reason_codes") if isinstance(payload, dict) else None
    if not raw:
        return ()
    return tuple(str(code) for code in raw if str(code).strip())


_ANSWER_ONLY_REASON_HINTS: dict[str, str] = {
    "answer_too_shallow": "显著加长，至少覆盖题目要求的各维度/角度。",
    "complex_answer_not_deep_enough": "补充案例、分情况分析与可执行建议，避免只列概念。",
    "deep_complex_requires_agent": "按复杂题标准展开：对比 + 取舍 + 场景化结论。",
    "case_analysis_missing": "至少给出 2–3 个分情况/scenario 分析。",
    "decision_not_made": "必须给出明确推荐/选型结论，不可只描述选项。",
    "structure_not_satisfied": "用清晰结构（分点或小标题）组织答案。",
    "comparison_not_performed": "对题目中的对象做逐项对比，不要只讲单方。",
}


def prepare_bundle_for_answer_only_refine(
    bundle: Any,
    *,
    reason_codes: tuple[str, ...] | list[str],
) -> Any:
    """Mark a bundle for round-1 depth-only regeneration (test/helper entrypoint).

    Mirrors what ``schedule_answer_only_refine`` records so ``AnswerAgent.huida``
    takes the answer-only path instead of the knowledge_grounded insufficiency template.
    """
    from dataclasses import is_dataclass, replace

    event = {
        "trigger": "quality_gate_refine",
        "requested_action": "answer_only_regenerate",
        "requested_by": "quality_gate",
        "stop_reason": "answer_only_refine_scheduled",
        "payload": {
            "refine_kind": "answer_only",
            "refine_reason_codes": [str(c) for c in reason_codes or ()],
        },
    }
    events = list(getattr(bundle, "autonomy_events", None) or [])
    events.append(event)
    if is_dataclass(bundle) and not isinstance(bundle, type):
        return replace(
            bundle,
            autonomy_events=events,
            used_rounds=[0, 1],
            final_answer_based_on_round="round_1",
            answer_limitations=[],
            material_sufficiency="sufficient",
            material_still_insufficient=False,
            insufficiency_signal="",
        )
    return bundle


def answer_only_success_exit_eligible(
    *,
    bundle: Any,
    quality_gate: Any | None,
    router_lane: str,
    use_knowledge: bool,
) -> bool:
    """Anti-gaming: flip partial→succeeded only after answer-only round-1 gate pass."""
    if not complex_refine_v2_active():
        return False
    if not is_answer_only_refine_bundle(bundle):
        return False
    if str(getattr(bundle, "final_answer_based_on_round", "") or "") != "round_1":
        return False
    if quality_gate is None or not bool(getattr(quality_gate, "pass_", False)):
        return False
    lane_l = str(router_lane or "").strip().lower()
    chunks = len(list(getattr(bundle, "retrieved_chunks", None) or []))
    if lane_l == "kb" or use_knowledge or chunks > 0:
        return False
    codes = set(getattr(quality_gate, "reason_codes", ()) or ())
    if codes & MATERIAL_REASON_CODES:
        return False
    mat = str(getattr(bundle, "material_sufficiency", "") or "").strip().lower()
    if mat == "insufficient" and bool(getattr(bundle, "material_still_insufficient", False)):
        signal = str(getattr(bundle, "insufficiency_signal", "") or "").strip().lower()
        hard = {
            "still_empty_after_gather",
            "required_material_missing_after_round1",
            "history_anchor_missing_source_id",
        }
        if signal in hard:
            return False
    return True


def reconcile_answer_only_turn_facts(
    facts: Any,
    *,
    bundle: Any,
    use_knowledge: bool,
) -> Any:
    """Clear stale partial/material exit signals after answer-only round-1 gate pass."""
    from dataclasses import replace

    from application.chat.chat_contracts import QualityGateResult
    from application.chat.pending_kind import PendingKind

    if not answer_only_success_exit_eligible(
        bundle=bundle,
        quality_gate=facts.quality_gate,
        router_lane=facts.router_lane,
        use_knowledge=use_knowledge,
    ):
        return facts
    qg = facts.quality_gate
    chunks = len(list(getattr(bundle, "retrieved_chunks", None) or []))
    cleaned_codes = tuple(
        _effective_answer_only_codes(
            qg.reason_codes if qg else (),
            [],
            lane=facts.router_lane,
            use_knowledge=use_knowledge,
            retrieved_chunks_count=chunks,
            kb_evidence_tier=str(getattr(bundle, "kb_evidence_tier", "") or ""),
        )
    )
    cleaned_gate = QualityGateResult(
        pass_=True,
        upgrade_profile=bool(getattr(qg, "upgrade_profile", False)) if qg else False,
        need_second_round=False,
        need_more_material=False,
        reason_codes=cleaned_codes,
    )
    return replace(
        facts,
        pending_kind=PendingKind.NONE,
        material_sufficiency="sufficient",
        quality_gate=cleaned_gate,
        answer_only_exit_reconcile=True,
    )


def exit_insufficient_evidence(envelope: Any) -> bool:
    """Canonical insufficiency predicate (single source for exit + metrics)."""
    mat = str(envelope.material_sufficiency or "").strip().lower()
    if mat in {"insufficient", "no_match", "low_confidence"}:
        return True
    codes = list(envelope.quality_gate.get("reason_codes") or [])
    return "kb_insufficient" in codes


def build_answer_only_executor_hint(*, reason_codes: tuple[str, ...] | list[str]) -> str:
    """Executor hint for round-1 depth regeneration (general-lane, no new material)."""
    lines = [
        "[refine/answer_only]",
        "【质量门二轮：仅重生成答案】",
        "这是 general-lane 纯推理/对比/设计题：无知识库或网页材料也可基于常识与工程经验作答。",
        "禁止输出「材料不足 / 无法确认 / 请补充资料 / 未检索到片段」等 insufficiency 拒答模板。",
        "必须：先给结论；按题目维度展开；给场景化建议；篇幅与深度明显超过上一轮。",
    ]
    for code in reason_codes or ():
        hint = _ANSWER_ONLY_REASON_HINTS.get(str(code))
        if hint:
            lines.append(f"- 针对 {code}：{hint}")
    return "\n".join(lines)
