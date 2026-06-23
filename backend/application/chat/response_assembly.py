from __future__ import annotations

from typing import Any

from application.chat.exit_signals import (
    set_material_sufficiency_signal,
    set_pending_kind_signal,
    set_primary_path_signal,
)
from application.chat.material_flow import material_trace_from_bundle
from application.chat.path_labels import resolve_complex_primary_path
from application.chat.pending_kind import resolve_pending_kind_for_bundle


def _resolve_extra_pending_kind(*, bundle: Any, history_snapshot: Any) -> str | None:
    resolved = resolve_pending_kind_for_bundle(
        bundle=bundle,
        history_snapshot=history_snapshot,
    )
    return resolved.value if resolved is not None else None


def _resolve_bundle_execution_status(bundle: Any) -> str:
    return str(getattr(bundle, "execution_status", "ok") or "ok")


def _build_source_diagnostics(*, pending_item: Any, commit_result: Any) -> dict[str, object]:
    source_diagnostics: dict[str, object] = {}
    if pending_item is not None:
        source_type = getattr(pending_item, "source_type", "")
        meta = getattr(pending_item, "metadata", {}) or {}
        source_diagnostics["source_type"] = source_type
        source_diagnostics["error_code"] = getattr(pending_item, "error_code", "") or ""
        if source_type in ("docx", "xlsx", "pdf", "txt", "md"):
            source_diagnostics.update({
                "lane": "document",
                "tool_name": meta.get("v16_tool_name", ""),
                "extract_method": meta.get("v16_extract_method", ""),
                "quality_level": meta.get("v16_quality_level", ""),
                "mcp_mode": meta.get("v16_mcp_mode", ""),
            })
        elif source_type == "web_url":
            source_diagnostics.update({
                "lane": "web",
                "tool_name": meta.get("v16_web_tool_name", ""),
                "fetch_method": meta.get("fetch_method", ""),
                "extraction_method": meta.get("extraction_method", ""),
                "quality_level": meta.get("quality_level", ""),
                "url": meta.get("url", ""),
                "domain": meta.get("domain", ""),
                "cookie_used": bool(meta.get("cookie_used", False)),
            })
        elif source_type in ("local_video", "web_video"):
            source_diagnostics.update({
                "lane": "video",
                "tool_name": meta.get("v16_video_tool_name", ""),
                "transcript_source": meta.get("transcript_source", "") or meta.get("text_source", ""),
                "quality_level": meta.get("quality_level", ""),
                "video_timings": {
                    "probe_elapsed_ms": int(meta.get("video_probe_elapsed_ms", 0) or 0),
                    "remaining_sync_budget_ms": int(meta.get("remaining_sync_budget_ms", 0) or 0),
                    "sync_strategy": str(meta.get("sync_strategy", "") or ""),
                },
            })
    if commit_result is not None:
        source_diagnostics["task_result_source_id"] = getattr(commit_result, "source_id", "") or ""
    return source_diagnostics


def _build_task_refs(*, pending_item: Any) -> list[dict[str, str]]:
    if pending_item is None:
        return []
    meta = getattr(pending_item, "metadata", {}) or {}
    pending_id = str(getattr(pending_item, "pending_id", "") or "")
    task_id = str(meta.get("task_id") or "")
    if not pending_id and not task_id:
        return []
    return [{
        "kind": str(getattr(pending_item, "source_type", "") or "pending"),
        "task_id": task_id,
        "pending_id": pending_id,
    }]


def _build_core_path_extra(*, message: str, plan: Any, bundle: Any, main_dec: Any, deps: Any, use_knowledge: bool, knowledge_block: str | None, web_block: str | None, collab_trace: list[str]) -> dict[str, Any]:
    primary_path = resolve_complex_primary_path(bundle)
    fp = deps.path_fingerprint(
        message, use_knowledge=use_knowledge,
        knowledge_block=knowledge_block, web_block=web_block,
    )
    return {
        "lane": primary_path,
        "router_lane": str(getattr(bundle, "router_lane", "") or ""),
        "answer_view_path": primary_path,
        "agno": True,
        "collaboration_trace": collab_trace,
        "v4_min_collab": True,
        "v4_path_fingerprint": fp,
        "v4_nodes": deps.nodes_contract(collab_trace),
        "v6_takeover": True,
        "v6_main_task_id": main_dec.task_id,
        "v6_middle_web_reason": bundle.web_judgment_reason,
        "v6_middle_material_insufficient": bundle.material_still_insufficient,
        "v6_plan_web_mode": plan.web_supplement_mode,
        "v6_plan_answer_composition": plan.answer_composition,
        "v6_plan_force_skip_evidence": plan.force_skip_evidence,
        "v6_middle_kb_tier": bundle.kb_evidence_tier,
        "v6_middle_insufficiency_signal": bundle.insufficiency_signal,
        "kb_sufficiency_level": getattr(bundle, "kb_sufficiency_level", "none"),
        "kb_sufficiency_reason_codes": list(getattr(bundle, "kb_sufficiency_reasons", ()) or ()),
    }


def _apply_v12_extra(*, extra: dict[str, Any], bundle: Any, use_knowledge: bool, web_block: str | None) -> list[Any]:
    rc = list(bundle.retrieved_chunks or [])
    if use_knowledge:
        extra["use_knowledge"] = True
        rag_len = sum(
            len(getattr(c, "to_context_line", lambda: "")()) for c in rc[:50]
        )
        rag_len += sum(len(t) for t in (bundle.temporary_materials or [])[:20])
        extra["rag_context_chars"] = rag_len
    if web_block:
        extra["web_search_used"] = True
        extra["web_evidence_chars"] = len(web_block)
    extra["v12_retrieved_chunks_count"] = len(rc)
    if rc:
        extra["v12_retrieval_debug"] = [
            {
                "source_id": getattr(c, "source_id", "?"),
                "chunk_id": getattr(c, "chunk_id", "?"),
                "score": getattr(c, "score", 0.0),
                "retrieval_strategy": getattr(c, "retrieval_strategy", ""),
            }
            for c in rc[:5]
        ]
        extra["v12_used_context"] = [
            getattr(c, "to_context_line", lambda: "")() for c in rc[:3]
        ]
    return rc


def _apply_v13_extra(*, extra: dict[str, Any], bundle: Any, history_snapshot: Any) -> tuple[Any, Any]:
    v13_status = getattr(bundle, "v13_material_status", "") or ""
    v13_pending = getattr(bundle, "pending_item", None)
    v13_commit = getattr(bundle, "v13_commit_result", None)
    if v13_status:
        extra["v13_material_status"] = v13_status
    if v13_status or getattr(bundle, "v13_source_type", ""):
        extra["v13_source_type"] = getattr(bundle, "v13_source_type", "")
    if getattr(bundle, "v13_used_pending_text", False):
        extra["v13_used_pending_text"] = True
    resolved_pending_kind = _resolve_extra_pending_kind(
        bundle=bundle,
        history_snapshot=history_snapshot,
    )
    if resolved_pending_kind is not None:
        set_pending_kind_signal(extra, resolved_pending_kind)
    if v13_pending is not None:
        extra["pending_source_id"] = getattr(v13_pending, "pending_id", "") or None
    if v13_commit is not None:
        extra["v13_commit"] = {
            "success": getattr(v13_commit, "success", False),
            "pending_id": getattr(v13_commit, "pending_id", ""),
            "source_id": getattr(v13_commit, "source_id", ""),
            "chunk_count": getattr(v13_commit, "chunk_count", 0),
            "error_code": getattr(v13_commit, "error_code", ""),
            "title": getattr(v13_commit, "title", ""),
            "source_type": getattr(v13_commit, "source_type", ""),
        }
    return v13_pending, v13_commit


def _apply_v15_observability_extra(*, extra: dict[str, Any], plan: Any, bundle: Any, main_dec: Any, retrieved_chunks: list[Any]) -> None:
    extra["v15_plan_id"] = str(getattr(main_dec, "task_id", "") or "")
    extra["v15_bundle_id"] = str(getattr(bundle, "bundle_id", "") or "")
    extra["v15_needs_retrieval"] = bool(getattr(plan, "needs_retrieval", False))
    extra["v15_retrieval_strategy"] = str(getattr(plan, "retrieval_strategy", "auto") or "auto")
    extra["v15_needs_pending"] = bool(getattr(plan, "needs_pending", False))
    extra["v15_pending_reference"] = str(getattr(plan, "pending_reference", "none") or "none")
    extra["v15_answer_mode"] = str(getattr(plan, "answer_mode", "direct") or "direct")
    v15_tools_allowed = getattr(plan, "tools_allowed", ())
    extra["v15_tools_allowed"] = list(v15_tools_allowed) if v15_tools_allowed else []
    extra["v15_material_sufficiency"] = str(getattr(bundle, "material_sufficiency", "sufficient") or "sufficient")
    extra["v15_execution_status"] = _resolve_bundle_execution_status(bundle)
    v15_failures = list(getattr(bundle, "failures", []) or [])
    if v15_failures:
        extra["v15_failures"] = v15_failures
    v15_tool_calls = list(getattr(bundle, "tool_calls", []) or [])
    if v15_tool_calls:
        extra["v15_tool_calls"] = v15_tool_calls
    # 统一观测口径：让 complex 路径也产出 capabilities_called（与 fast 路径同字段），
    # 便于 smoke/治理只读一处。v15_tool_calls 保留为带 strategy/hits 的明细。
    _tc_names: list[str] = []
    for _tc in v15_tool_calls:
        if isinstance(_tc, dict):
            _name = str(_tc.get("tool") or _tc.get("tool_name") or "").strip()
        else:
            _name = str(_tc or "").strip()
        if _name and _name not in _tc_names:
            _tc_names.append(_name)
    if _tc_names:
        _existing_caps = list(extra.get("capabilities_called") or [])
        for _n in _tc_names:
            if _n not in _existing_caps:
                _existing_caps.append(_n)
        extra["capabilities_called"] = _existing_caps
    v15_temp = list(getattr(bundle, "temporary_materials", []) or [])
    if v15_temp:
        extra["v15_temporary_materials_count"] = len(v15_temp)
        extra["v15_temporary_materials_preview"] = [(t or "")[:200] for t in v15_temp[:2]]
    v15_commits = list(getattr(bundle, "commit_results", []) or [])
    if v15_commits:
        extra["v15_commit_results"] = v15_commits
    extra["v15_retrieved_chunks_count"] = len(retrieved_chunks)
    if retrieved_chunks:
        from services.capabilities.knowledge.retrieval_provenance import count_user_committed_hits

        committed_hits = count_user_committed_hits(retrieved_chunks)
        extra["user_committed_hits_count"] = committed_hits
        extra["user_committed_retrieval_hit"] = committed_hits > 0
    plan_retrieval_filters = getattr(plan, "retrieval_filters", None)
    if plan_retrieval_filters:
        extra["v15_retrieval_filters"] = plan_retrieval_filters
    if retrieved_chunks:
        first_chunk_meta = getattr(retrieved_chunks[0], "metadata", {}) or {}
        if first_chunk_meta.get("source_id") or getattr(retrieved_chunks[0], "source_id", ""):
            extra["v15_retrieved_source_id"] = getattr(retrieved_chunks[0], "source_id", "")


def _apply_v17_extra(
    *,
    extra: dict[str, Any],
    bundle: Any,
    plan: Any,
    answer_text: str,
    message: str,
) -> None:
    v17_trace = dict(getattr(bundle, "negotiation_trace", {}) or {})
    if not v17_trace:
        return
    extra.update(v17_trace)
    extra["analysis_job"] = getattr(bundle, "analysis_job", None)
    extra["tool_plan"] = getattr(plan, "tool_plan", None)
    extra["fallback_steps"] = list(getattr(plan, "fallback_steps", ()) or [])
    extra["tools_allowed"] = list(
        (getattr(plan, "tool_plan", None) or {}).get("tools_allowed", [])
        or list(getattr(plan, "tools_allowed", ()) or [])
    )
    extra["tools_disabled"] = list(getattr(plan, "tools_disabled", ()) or [])
    extra["privacy_scope"] = str(
        getattr(plan, "privacy_scope", "")
        or ((getattr(plan, "tool_plan", None) or {}).get("privacy_scope", ""))
    )
    extra["budget_policy"] = dict(
        getattr(plan, "budget_policy", None)
        or ((getattr(plan, "tool_plan", None) or {}).get("budget_policy", {}) or {})
    )
    extra["max_rounds"] = int(
        getattr(plan, "max_rounds", 0)
        or ((getattr(plan, "tool_plan", None) or {}).get("max_rounds", 0) or 0)
    )
    extra["original_user_intent"] = str(getattr(plan, "original_user_intent", "") or message)
    extra["source_tasks"] = list(getattr(bundle, "source_tasks", []) or [])
    extra["source_briefs"] = list(getattr(bundle, "source_briefs", []) or [])
    extra["comparison_matrix"] = getattr(bundle, "comparison_matrix", None)
    extra["used_context"] = list(getattr(bundle, "used_context", []) or [])
    extra["material_sufficiency"] = getattr(bundle, "material_sufficiency", "insufficient")
    extra["final_answer"] = answer_text


def _apply_loop_observability_extra(*, extra: dict[str, Any], bundle: Any) -> None:
    if getattr(bundle, "critic_check", None) is not None:
        extra["critic_check"] = getattr(bundle, "critic_check", None)
    if getattr(bundle, "feedback_request", None) is not None:
        extra["feedback_request"] = getattr(bundle, "feedback_request", None)
    if getattr(bundle, "feedback_gate_result", None) is not None:
        extra["feedback_gate_result"] = getattr(bundle, "feedback_gate_result", None)
    if getattr(bundle, "round_delta", None) is not None:
        extra["round_delta"] = getattr(bundle, "round_delta", None)
    if getattr(bundle, "used_rounds", None):
        extra["used_rounds"] = list(getattr(bundle, "used_rounds", []) or [])
    if getattr(bundle, "autonomy_loop_id", None):
        extra["loop_id"] = getattr(bundle, "autonomy_loop_id", "")
    if getattr(bundle, "autonomy_events", None):
        extra["autonomy_events"] = list(getattr(bundle, "autonomy_events", []) or [])
        if extra["autonomy_events"]:
            extra["round_index"] = int(extra["autonomy_events"][-1].get("round_index", 0) or 0)
    if getattr(bundle, "answer_check", None):
        extra["answer_check"] = getattr(bundle, "answer_check", "pass")
    if getattr(bundle, "revise_requested", None) is not None:
        extra["revise_requested"] = bool(getattr(bundle, "revise_requested", False))
    if getattr(bundle, "retry_requested", None) is not None:
        extra["retry_requested"] = bool(getattr(bundle, "retry_requested", False))
    if getattr(bundle, "more_evidence_requested", None) is not None:
        extra["more_evidence_requested"] = bool(getattr(bundle, "more_evidence_requested", False))
    if getattr(bundle, "stop_reason", None):
        extra["stop_reason"] = getattr(bundle, "stop_reason", "")
    if getattr(bundle, "used_rounds", None):
        extra["loop_total_rounds"] = len(list(getattr(bundle, "used_rounds", []) or []))
    if getattr(bundle, "retry_count", None) is not None:
        extra["retry_count"] = int(getattr(bundle, "retry_count", 0) or 0)
    if getattr(bundle, "answer_limitations", None):
        extra["limitations"] = list(getattr(bundle, "answer_limitations", []) or [])
    if getattr(bundle, "final_answer_based_on_round", None):
        extra["final_answer_based_on_round"] = getattr(bundle, "final_answer_based_on_round", "round_0")


def _apply_trace_observability_extra(*, extra: dict[str, Any], collab_trace: list[str]) -> None:
    for trace_line in collab_trace:
        if isinstance(trace_line, str) and trace_line.startswith("v14:middle:"):
            extra["v14_retrieval_trace_line"] = trace_line
            break
    for trace_line in collab_trace:
        if isinstance(trace_line, str) and trace_line.startswith("v14r2:middle:"):
            extra["v14_score_trace_line"] = trace_line
            break


def _apply_source_observability_extra(*, extra: dict[str, Any], pending_item: Any, commit_result: Any) -> None:
    source_diagnostics = _build_source_diagnostics(
        pending_item=pending_item,
        commit_result=commit_result,
    )
    if source_diagnostics:
        extra["source_diagnostics"] = source_diagnostics

    task_refs = _build_task_refs(pending_item=pending_item)
    if task_refs:
        extra["task_refs"] = task_refs


def build_extra(
    message: str,
    plan: Any,
    bundle: Any,
    main_dec: Any,
    answer_text: str,
    deps: Any,
    *,
    use_knowledge: bool,
    knowledge_block: str | None,
    web_block: str | None,
    collab_trace: list[str],
    history_snapshot: Any,
) -> dict[str, Any]:
    """Assemble the extra dict for the response."""
    extra: dict[str, Any] = _build_core_path_extra(
        message=message,
        plan=plan,
        bundle=bundle,
        main_dec=main_dec,
        deps=deps,
        use_knowledge=use_knowledge,
        knowledge_block=knowledge_block,
        web_block=web_block,
        collab_trace=collab_trace,
    )
    set_primary_path_signal(
        extra,
        str(extra.get("answer_view_path") or resolve_complex_primary_path(bundle)),
    )
    from application.chat.turn_response_builder import merge_agent_extra_into_turn_extra

    collab_fn = getattr(deps.answer_agent, "collab_extra", None) or getattr(
        deps.answer_agent, "xiezuo_extra", lambda *_a, **_k: {}
    )
    extra = merge_agent_extra_into_turn_extra(extra, collab_fn(plan, bundle))
    _rc = _apply_v12_extra(
        extra=extra,
        bundle=bundle,
        use_knowledge=use_knowledge,
        web_block=web_block,
    )

    v13_pending, v13_commit = _apply_v13_extra(
        extra=extra,
        bundle=bundle,
        history_snapshot=history_snapshot,
    )

    _apply_v15_observability_extra(
        extra=extra,
        plan=plan,
        bundle=bundle,
        main_dec=main_dec,
        retrieved_chunks=_rc,
    )
    _apply_loop_observability_extra(extra=extra, bundle=bundle)

    _apply_v17_extra(
        extra=extra,
        bundle=bundle,
        plan=plan,
        answer_text=answer_text,
        message=message,
    )
    _apply_trace_observability_extra(extra=extra, collab_trace=collab_trace)
    _apply_source_observability_extra(
        extra=extra,
        pending_item=v13_pending,
        commit_result=v13_commit,
    )

    set_material_sufficiency_signal(
        extra,
        str(getattr(bundle, "material_sufficiency", "sufficient") or "sufficient"),
    )
    extra.update(material_trace_from_bundle(bundle, use_knowledge=use_knowledge))

    return extra
