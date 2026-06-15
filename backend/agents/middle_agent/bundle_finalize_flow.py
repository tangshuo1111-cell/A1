"""台账 G-005「bundle_finalize_flow」：Middle invoke 末段 trace 拼装 + V15 bundle 派生字段。

与 `v13_pending_flow` 的交界：`build_trace_lines_pre_v13` 产出截至 V12 的 trace，
随后由 `run_v13_prepare_commit_phase` 往同一 `lines` 追加 V13 行，再调
`finalize_bundle_after_v13` 追加回答收口 trace 并计算 V15 聚合字段。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agents.main_agent import AgnoCollaborationPlan
from agents.shared.history_context import PrevVideoRef
from application.chat.chat_contracts import KbSufficiencyResult
from schemas import MainDecision
from video.url_fetch import FetchVideoResult

from .material_policy import _agno_route_label
from .material_sufficiency import evaluate_material_sufficiency
from .schema import CailiaoPan

_HARD_BLOCKING_FAILURE_REASONS = {
    "not_allowed_by_plan",
    "tool_not_found",
    "tool_disabled",
}
_HARD_BLOCKING_FAILURE_SUBSTRINGS = (
    "prepare/commit failed",
    "source_all_missing_source_id",
    "file_not_found",
)


def _is_blocking_failure(item: dict[str, Any]) -> bool:
    reason = str(item.get("reason") or item.get("failure_reason") or "").strip().lower()
    if not reason:
        return False
    if reason in _HARD_BLOCKING_FAILURE_REASONS:
        return True
    return any(token in reason for token in _HARD_BLOCKING_FAILURE_SUBSTRINGS)


def build_trace_lines_pre_v13(
    *,
    message: str,
    http_use_knowledge: bool,
    plan: AgnoCollaborationPlan,
    decision: MainDecision,
    intent: str,
    try_rag: bool,
    knowledge_block: str | None,
    v14_trace_info: dict[str, Any] | None,
    web_reason: str,
    want_web: bool,
    web_block: str | None,
    cailiao_pan: CailiaoPan,
    knowledge_adequate: bool,
    kb_tier: str,
    material_insufficient: bool,
    signal: str,
    video_yitu: dict[str, Any],
    mcp_video_decision: str,
    mcp_video_ok: bool,
    mcp_video_source: str | None,
    mcp_video_text: str | None,
    mcp_video_error: str,
    mcp_video_pending_id: str | None,
    mcp_video_ingest_error: str,
    video_url_yitu: dict[str, Any],
    video_url_from: str,
    video_url_decision: str,
    video_url_result: FetchVideoResult | None,
    video_url_ingest_source_id: str | None,
    video_url_ingest_chunks: int,
    video_url_ingest_error: str,
    video_url_kb_block: str | None,
    video_url_tidy_status: str,
    video_url_tidy_model: str,
    v8_history_used: bool,
    v8_anchor: PrevVideoRef | None,
    v8_history_anchor_status: str,
    retrieved_chunks: list[Any],
) -> list[str]:
    route = _agno_route_label(message, http_use_knowledge=http_use_knowledge)
    force_skip = plan.force_skip_evidence
    lines: list[str] = [
        f"v6:main:channel={decision.answer_channel}",
        f"v6:main:need_rag={decision.need_rag}",
        f"v6:middle:try_rag={try_rag}",
        f"v6:middle:route_label={route}",
        f"v6:middle:force_skip_evidence={force_skip}",
        f"v6:middle:intent={intent}",
        (
            f"v6:main:plan_web_mode={plan.web_supplement_mode}"
            f"|composition={plan.answer_composition}"
        ),
        f"v4:1_route:{route}",
    ]
    if try_rag:
        lines.append("v4:2_gather:rag_call")
        lines.append("v4:2_gather:rag_hit" if knowledge_block else "v4:2_gather:rag_miss")
        _v14_ti = v14_trace_info
        if _v14_ti is not None:
            _fa = _v14_ti.get("filters_applied") or {}
            lines.append(
                f"v14:middle:strategy_requested={_v14_ti.get('strategy_requested', 'auto')} "
                f"strategy_used={_v14_ti.get('strategy_used', '')} "
                f"hits={_v14_ti.get('hits', 0)} "
                f"no_match={_v14_ti.get('no_match', False)} "
                f"low_confidence={_v14_ti.get('low_confidence', False)} "
                f"filters_applied={_fa} "
                f"auto_reason={_v14_ti.get('auto_reason', '')!r}"
            )
            if _v14_ti.get("hits", 0) > 0:
                lines.append(
                    f"v14r2:middle:score_max_kw={_v14_ti.get('score_max_keyword', 0.0):.3f} "
                    f"score_max_sem={_v14_ti.get('score_max_semantic', 0.0):.3f} "
                    f"score_max_combined={_v14_ti.get('score_max_combined', 0.0):.3f} "
                    f"alpha={_v14_ti.get('alpha', 0.0):.2f}"
                )
    else:
        lines.append("v4:2_gather:rag_skip")
    lines.append("v4:2_gather:web_gate")
    lines.append(f"v6:middle:web_decision={web_reason}")
    if want_web:
        lines.append("v4:2_gather:web_call")
        lines.append("v4:2_gather:web_hit" if web_block else "v4:2_gather:web_empty")
    else:
        lines.append("v4:2_gather:web_skip")
    lines.append(
        f"v6:middle:cailiao gou={cailiao_pan.gou} bukong={cailiao_pan.bukong_xinhao} "
        f"laiyuan={cailiao_pan.laiyuan_zhu} kb_qiangdu={cailiao_pan.kb_qiangdu:.3f} "
        f"que={cailiao_pan.que_shenme} xia={cailiao_pan.xia_yi_bu}"
    )
    lines.append(
        f"v6:middle:kb_adequate={knowledge_adequate} kb_tier={kb_tier} "
        f"material_insufficient={material_insufficient} signal={signal}"
    )
    lines.append(f"v7:middle:video_yitu={video_yitu['yitu_label']}")
    lines.append(f"v7:middle:mcp_video_decision={mcp_video_decision}")
    if mcp_video_decision == "call_video_to_text":
        lines.append("v7:middle:mcp_video_call=video_to_text")
        if mcp_video_ok:
            lines.append(
                f"v7:middle:mcp_video_ok=true source={mcp_video_source} "
                f"chars={len(mcp_video_text or '')}"
            )
        else:
            lines.append(f"v7:middle:mcp_video_ok=false error={mcp_video_error[:160]}")
    else:
        lines.append("v7:middle:mcp_video_call=skip")
    if mcp_video_decision == "call_video_to_text" and mcp_video_ok:
        if mcp_video_pending_id:
            lines.append(
                f"v7:middle:pending_ok=true pending_id={mcp_video_pending_id} "
                f"source_type=local_video committed=False"
            )
        else:
            lines.append(f"v7:middle:pending_ok=false error={mcp_video_ingest_error[:160]}")
    else:
        lines.append("v7:middle:pending=skip")
    lines.append(f"v11_middle:video_url_yitu={video_url_yitu['yitu_label']}")
    lines.append(f"v11_middle:video_url_from={video_url_from}")
    lines.append(f"v11_middle:video_url_decision={video_url_decision}")
    if video_url_decision == "call_url_fetch_video":
        cookies_used = "none"
        if video_url_result is not None:
            cu = (video_url_result.extra or {}).get("cookies")
            if isinstance(cu, str) and cu:
                cookies_used = cu.replace(" ", "_")
        lines.append(f"v11_middle:video_url_cookies={cookies_used}")
        if video_url_result is not None:
            _ex = video_url_result.extra or {}
            for _src_key, _trace_key in (
                ("elapsed_ms", "elapsed_ms"),
                ("metadata_ms", "metadata_ms"),
                ("subtitle_ms", "subtitle_ms"),
                ("audio_ms", "audio_ms"),
                ("asr_ms", "asr_ms"),
            ):
                _v = _ex.get(_src_key)
                if _v not in (None, ""):
                    lines.append(f"v11_middle:video_url_{_trace_key}={str(_v).replace(' ', '_')}")
        if video_url_result is not None and video_url_result.success:
            lines.append("v11_middle:video_url_ok=true")
            lines.append(f"v11_middle:video_url_text_source={video_url_result.text_source}")
            lines.append(f"v11_middle:video_url_chars={len(video_url_result.text)}")
            if video_url_result.text_source == "asr":
                if video_url_result.asr_provider:
                    lines.append(
                        f"v11_middle:video_url_asr_provider={video_url_result.asr_provider}"
                    )
                if video_url_result.asr_model:
                    lines.append(
                        f"v11_middle:video_url_asr_model={video_url_result.asr_model}"
                    )
        else:
            stage = video_url_result.stage if video_url_result else "unknown"
            err = (video_url_result.error if video_url_result else "no_result")[:160]
            err_safe = err.replace(" ", "_").replace("\n", "_")
            lines.append("v11_middle:video_url_ok=false")
            lines.append(f"v11_middle:video_url_stage={stage}")
            lines.append(f"v11_middle:video_url_error={err_safe}")
        if video_url_ingest_source_id:
            if video_url_ingest_chunks > 0 and not video_url_ingest_error:
                lines.append("v11_middle:video_url_ingest_ok=true")
                lines.append(
                    f"v11_middle:video_url_ingest_source_id={video_url_ingest_source_id}"
                )
                lines.append(f"v11_middle:video_url_ingest_chunks={video_url_ingest_chunks}")
            else:
                err_safe = (video_url_ingest_error or "unknown")[:160].replace(
                    " ", "_"
                ).replace("\n", "_")
                lines.append("v11_middle:video_url_ingest_ok=false")
                lines.append(f"v11_middle:video_url_ingest_error={err_safe}")
        else:
            lines.append("v11_middle:video_url_ingest_skip=r6_instant")
        if video_url_kb_block:
            lines.append("v11_middle:video_url_kb_block=fresh")
        lines.append(f"v11_middle:video_url_tidy={video_url_tidy_status}")
        if video_url_tidy_model:
            lines.append(f"v11_middle:video_url_tidy_model={video_url_tidy_model}")
    else:
        lines.append("v11_middle:video_url_ingest=skip")
    if v8_history_used and v8_anchor is not None:
        lines.append(f"v8:middle:history_used=true followup_anchor={v8_anchor.source_id}")
    else:
        lines.append("v8:middle:history_used=false")
    lines.append(f"v8:middle:history_anchor={v8_history_anchor_status}")
    lines.append(f"v12:middle:retrieved_chunks={len(retrieved_chunks)}")
    if retrieved_chunks:
        for _i, _c in enumerate(retrieved_chunks[:3]):
            _sid = getattr(_c, "source_id", "?")
            _cid = getattr(_c, "chunk_id", "?")
            _score = getattr(_c, "score", 0.0)
            lines.append(
                f"v12:middle:chunk[{_i}] source_id={_sid} chunk_id={_cid} score={_score:.4f}"
            )
    return lines


@dataclass(frozen=True)
class MiddleV15BundleFacet:
    plan_id: str
    execution_status: str
    tool_calls: list[dict[str, Any]]
    temporary_materials: list[str]
    commit_results: list[dict[str, Any]]
    failures: list[dict[str, Any]]
    material_sufficiency: str
    v11_saved_to_kb: bool
    v11_saved_source_id: str | None
    v11_saved_title: str | None


def finalize_bundle_after_v13(
    *,
    lines: list[str],
    plan: AgnoCollaborationPlan,
    blocked_failures: list[dict[str, Any]],
    needs_retrieval_plan: Any,
    try_rag: bool,
    knowledge_block: str | None,
    retrieved_chunks: list[Any],
    want_web: bool,
    web_block: str | None,
    mcp_video_ok: bool,
    mcp_video_source: str | None,
    mcp_video_error: str,
    web_video_pending_early: Any | None,
    early_web_video_url_normalized: str,
    pending_item_obj: Any | None,
    mcp_video_pending_item: Any | None,
    mcp_video_pending_id: str | None,
    v13_commit_result_obj: Any | None,
    v13_material_status: str,
    material_insufficient: bool,
    kb_sufficiency: KbSufficiencyResult | None,
    v14_trace_info: dict[str, Any] | None,
    inline_document_text: str | None = None,
) -> MiddleV15BundleFacet:
    lines.append("v4:3_answer:agno_unified")

    for _blocked in blocked_failures:
        _tool = (
            _blocked.get("tool")
            or _blocked.get("worker")
            or _blocked.get("tool_name")
            or _blocked.get("outcome")
            or "unknown"
        )
        _reason = _blocked.get("reason") or _blocked.get("failure_reason") or "blocked"
        lines.append(
            f"v15:tool_blocked tool={_tool} reason={_reason}"
        )
    lines.append(
        f"v15:needs_retrieval_plan={needs_retrieval_plan} "
        f"try_rag_after_plan_override={try_rag}"
    )

    _v15_plan_id = str(getattr(getattr(plan, "decision", None), "task_id", "") or "")
    _v15_tool_calls: list[dict[str, Any]] = []
    if retrieved_chunks:
        _v15_tool_calls.append({
            "tool": "retrieve_knowledge",
            "strategy": getattr(plan, "retrieval_strategy", "auto"),
            "hits": len(retrieved_chunks),
            "ok": True,
        })
    if mcp_video_ok:
        _v15_tool_calls.append({
            "tool": "mcp_video_to_text",
            "source": mcp_video_source or "",
            "ok": True,
        })
    if web_video_pending_early is not None:
        _v15_tool_calls.append({
            "tool": "prepare_web_video",
            "source": early_web_video_url_normalized or "",
            "ok": True,
        })
    if want_web and web_block:
        _v15_tool_calls.append({"tool": "fetch_web", "ok": True})

    _v15_temporary_materials: list[str] = []
    if pending_item_obj is not None:
        _item_obj = pending_item_obj
        _item_text = getattr(_item_obj, "text", "") or ""
        _item_title = getattr(_item_obj, "title", "") or ""
        _item_status = getattr(_item_obj, "status", "")
        if _item_text:
            _v15_temporary_materials.append(
                f"[临时材料 pending_id={getattr(_item_obj, 'pending_id', '')[:8]} "
                f"title={_item_title} status={_item_status}]\n{_item_text[:2000]}"
            )
    if mcp_video_pending_item is not None:
        _mcp_preview = (
            getattr(mcp_video_pending_item, "preview_text", "")
            or getattr(mcp_video_pending_item, "text", "")
            or ""
        )
        if _mcp_preview:
            _pid = mcp_video_pending_id[:8] if mcp_video_pending_id else ""
            _v15_temporary_materials.append(
                f"[MCP视频待保存 pending_id={_pid} "
                f"source_type=local_video committed=False]\n{_mcp_preview[:2000]}"
            )

    from application.chat.inline_document_material import append_inline_document_temporary_material

    append_inline_document_temporary_material(
        _v15_temporary_materials,
        inline_document_text=inline_document_text,
    )

    _v15_commit_results: list[dict[str, Any]] = []
    if v13_commit_result_obj is not None:
        _cr = v13_commit_result_obj
        _v15_commit_results.append({
            "source_id": getattr(_cr, "source_id", "") or "",
            "chunks": getattr(_cr, "chunk_count", 0),
            "status": "committed" if getattr(_cr, "success", False) else "failed",
            "title": getattr(_cr, "title", "") or "",
            "error_code": getattr(_cr, "error_code", "") or "",
        })

    _v15_failures: list[dict[str, Any]] = list(blocked_failures)
    if mcp_video_error and mcp_video_error != "not_allowed_by_plan":
        _v15_failures.append({
            "tool": "mcp_video_to_text",
            "reason": mcp_video_error,
            "recoverable": False,
        })
    _prep_commit_blocked = any(
        (
            str(
                f.get("tool")
                or f.get("worker")
                or f.get("tool_name")
                or f.get("outcome")
                or ""
            ).startswith("prepare_")
        )
        or (
            str(
                f.get("tool")
                or f.get("worker")
                or f.get("tool_name")
                or f.get("outcome")
                or ""
            ) == "commit_pending"
        )
        for f in blocked_failures
    )
    if v13_material_status == "failed" and not _prep_commit_blocked:
        _v15_failures.append({
            "tool": "v13_prepare_commit",
            "reason": "prepare/commit failed",
            "recoverable": True,
        })

    _v15_material_sufficiency = evaluate_material_sufficiency(
        try_rag=try_rag,
        knowledge_block=knowledge_block,
        web_block=web_block,
        retrieved_chunks_count=len(retrieved_chunks),
        temporary_materials_count=len(_v15_temporary_materials),
        commit_results_count=len(_v15_commit_results),
        kb_sufficiency=kb_sufficiency,
        material_insufficient=material_insufficient,
        retrieval_trace_info=v14_trace_info,
    ).level

    v11_saved_to_kb = False
    v11_saved_source_id: str | None = None
    v11_saved_title: str | None = None
    if v13_commit_result_obj is not None and getattr(v13_commit_result_obj, "success", False):
        _cr_fb = v13_commit_result_obj
        v11_saved_to_kb = True
        _sid_fb = getattr(_cr_fb, "source_id", None)
        if _sid_fb:
            v11_saved_source_id = str(_sid_fb)
        _tit_fb = getattr(_cr_fb, "title", None)
        if _tit_fb:
            v11_saved_title = str(_tit_fb)

    _blocking_failures = [f for f in _v15_failures if _is_blocking_failure(f)]

    if _blocking_failures and not (
        retrieved_chunks or _v15_temporary_materials or _v15_commit_results or web_block
    ):
        _v15_execution_status = "failed"
    elif _blocking_failures:
        _v15_execution_status = "partial"
    else:
        _v15_execution_status = "ok"

    _v15_answer_mode = getattr(plan, "answer_mode", "direct") or "direct"
    _v15_tools_allowed = ",".join(getattr(plan, "tools_allowed", ()) or ())
    lines.append(
        f"v15:plan plan_id={_v15_plan_id} "
        f"needs_retrieval={getattr(plan, 'needs_retrieval', False)} "
        f"retrieval_strategy={getattr(plan, 'retrieval_strategy', 'auto')} "
        f"needs_pending={getattr(plan, 'needs_pending', False)} "
        f"pending_reference={getattr(plan, 'pending_reference', 'none')} "
        f"answer_mode={_v15_answer_mode} "
        f"tools_allowed={_v15_tools_allowed!r}"
    )
    lines.append(
        f"v15:bundle execution_status={_v15_execution_status} "
        f"tool_calls={len(_v15_tool_calls)} "
        f"temporary_materials={len(_v15_temporary_materials)} "
        f"commit_results={len(_v15_commit_results)} "
        f"failures={len(_v15_failures)} "
        f"material_sufficiency={_v15_material_sufficiency}"
    )

    return MiddleV15BundleFacet(
        plan_id=_v15_plan_id,
        execution_status=_v15_execution_status,
        tool_calls=_v15_tool_calls,
        temporary_materials=_v15_temporary_materials,
        commit_results=_v15_commit_results,
        failures=_v15_failures,
        material_sufficiency=_v15_material_sufficiency,
        v11_saved_to_kb=v11_saved_to_kb,
        v11_saved_source_id=v11_saved_source_id,
        v11_saved_title=v11_saved_title,
    )
