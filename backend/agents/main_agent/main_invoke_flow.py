"""Main invoke_executor 主链（V13/V17/plan 组装）。

从 `runtime.py` 抽出，保持 ``MainAgentRuntime.invoke_executor`` 行为不变。
拆分为 _classify_v13 / _build_plan_params / run_main_invoke_executor 三段。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agents._runtime import AgentRunFrame
from agents.multisource import build_analysis_job, build_tool_audit_job, extract_url_sources
from agents.shared.history_context import SessionHistorySnapshot
from application.chat.complexity_policy import (
    evaluate_complex_candidate,
    is_analysis_request,
    is_save_request,
)
from debug_trace import trace
from entry.task_dispatcher import issue_task_id
from services.capabilities.web import web_orchestration_service as agno_web_service

from .main_fallback_rules import (
    v13_fallback_commit_intent,
    v13_fallback_prepare_file,
    v13_fallback_prepare_local_video,
    v13_fallback_prepare_web_url,
    v13_fallback_prepare_web_video,
)
from .schema import (
    AgnoCollaborationPlan,
    ExecutionAgentSpec,
    ExecutionPlan,
    V13PrepareIntent,
)

try:
    from llm import router as _llm_router
except ImportError:
    _llm_router = None


# ---------------------------------------------------------------------------
# Sub-function 1: V13 intent classification + fallback
# ---------------------------------------------------------------------------


@dataclass
class _V13Result:
    prepare_intent: V13PrepareIntent | None
    commit_intent: bool
    llm_signal: str
    llm_error: str


def _classify_v13(msg: str, inputs: dict[str, Any]) -> _V13Result:
    """V13 意图分类 + 规则 fallback。"""
    prepare_intent_val: V13PrepareIntent | None = None
    commit_intent_val = False
    llm_signal = "skip"
    llm_error = ""

    v13_classifier = inputs.get("v13_intent_classifier")
    if v13_classifier is None and _llm_router is not None:
        v13_classifier = getattr(_llm_router, "classify_v13_intent_with_llm", None)

    if v13_classifier is not None:
        try:
            v13_result = v13_classifier(msg)
            if getattr(v13_result, "available", False):
                v13_intent_str = getattr(v13_result, "intent", "none")
                llm_signal = f"llm:{v13_intent_str}"
                if v13_intent_str == "commit_pending":
                    commit_intent_val = True
                elif v13_intent_str in (
                    "prepare_text", "prepare_file", "prepare_web_url",
                    "prepare_local_video", "prepare_web_video",
                ):
                    v3_raw_src = getattr(v13_result, "raw_source", "") or ""
                    _stype_map = {
                        "prepare_text": "text",
                        "prepare_file": "text_file",
                        "prepare_web_url": "web_url",
                        "prepare_local_video": "local_video",
                        "prepare_web_video": "web_video",
                    }
                    v3_src_type = _stype_map.get(v13_intent_str, "")
                    _has_content = v13_intent_str == "prepare_text" and len(msg) > 30
                    prepare_intent_val = V13PrepareIntent(
                        source_type=v3_src_type,
                        raw_source=v3_raw_src,
                        has_content=_has_content,
                    )
            else:
                llm_error = getattr(v13_result, "error", "unavailable")
                llm_signal = f"llm_unavailable:{llm_error}"
        except (OSError, ValueError, RuntimeError, ImportError) as _e:
            llm_signal = f"llm_exception:{type(_e).__name__}"
            llm_error = str(_e)[:80]

    # Fallback when LLM unavailable
    _fallback_needed = (
        "llm_unavailable" in llm_signal
        or "llm_exception" in llm_signal
        or llm_signal == "skip"
    )
    if _fallback_needed:
        try:
            _local_vid_triggered, _local_vid_path = v13_fallback_prepare_local_video(msg)
            if _local_vid_triggered:
                prepare_intent_val = V13PrepareIntent(
                    source_type="local_video",
                    raw_source=_local_vid_path,
                    has_content=False,
                )
                llm_signal = "fallback:prepare_local_video"
            else:
                _web_vid_triggered, _vid_url = v13_fallback_prepare_web_video(msg)
                if _web_vid_triggered and _vid_url:
                    prepare_intent_val = V13PrepareIntent(
                        source_type="web_video",
                        raw_source=_vid_url,
                        has_content=False,
                    )
                    llm_signal = "fallback:prepare_web_video"
                else:
                    if v13_fallback_commit_intent(msg):
                        commit_intent_val = True
                        llm_signal = "fallback:commit"
                    else:
                        _web_triggered, _url = v13_fallback_prepare_web_url(msg)
                        if _web_triggered and _url:
                            prepare_intent_val = V13PrepareIntent(
                                source_type="web_url",
                                raw_source=_url,
                                has_content=False,
                            )
                            llm_signal = "fallback:prepare_web_url"
                        else:
                            _file_triggered, _fname = v13_fallback_prepare_file(msg)
                            if _file_triggered:
                                prepare_intent_val = V13PrepareIntent(
                                    source_type="text_file",
                                    raw_source=_fname,
                                    has_content=False,
                                )
                                llm_signal = "fallback:prepare_file"
        except (OSError, ValueError, RuntimeError, TypeError) as _e2:
            llm_signal = f"fallback_exception:{type(_e2).__name__}"

    if v13_fallback_commit_intent(msg):
        commit_intent_val = True

    # web_url 预备纠偏：含 URL 的「分析/对比/总结要点」任务是取证分析，不是「抓取保存」。
    # 若被分类成 prepare_web_url 但消息明显是分析诉求且无保存意图，则丢弃预备意图，
    # 让它走正常网页取证链路（支持静态/动态抓取），避免产出「temporary_materials 为空」。
    if (
        prepare_intent_val is not None
        and getattr(prepare_intent_val, "source_type", "") == "web_url"
        and not commit_intent_val
    ) and is_analysis_request(msg) and not is_save_request(msg):
        prepare_intent_val = None
        llm_signal = f"{llm_signal}+web_url_analysis_demote"

    # 上传链路兜底：当本轮带了文件字节（/agno/upload）时，message 里通常没有文件名，
    # LLM/正则给出的 raw_source 会丢扩展名，导致 prepare_file 走不到 pdf/docx 解析器。
    # 用 v13_title（完整文件名，含扩展名）作为 text_file 的 raw_source，保证下游按扩展名分发。
    _uploaded_content = inputs.get("v13_file_content")
    _uploaded_title = str(inputs.get("v13_title") or "").strip()
    if _uploaded_content is not None and _uploaded_title and not commit_intent_val:
        _intent_src = (
            getattr(prepare_intent_val, "source_type", "")
            if prepare_intent_val is not None
            else ""
        )
        _intent_raw = (
            str(getattr(prepare_intent_val, "raw_source", "") or "")
            if prepare_intent_val is not None
            else ""
        )
        # 仅在「无 prepare 意图」或「已是 text_file 但 raw_source 缺扩展名」时补 title。
        _raw_has_ext = bool(_intent_raw) and "." in _intent_raw.rsplit("/", 1)[-1]
        if prepare_intent_val is None or (
            _intent_src in ("", "text", "text_file") and not _raw_has_ext
        ):
            prepare_intent_val = V13PrepareIntent(
                source_type="text_file",
                raw_source=_uploaded_title,
                has_content=True,
            )
            llm_signal = f"{llm_signal}+upload_title_fallback"

    return _V13Result(
        prepare_intent=prepare_intent_val,
        commit_intent=commit_intent_val,
        llm_signal=llm_signal,
        llm_error=llm_error,
    )


# ---------------------------------------------------------------------------
# Sub-function 2: Build tool list + answer mode + V17 job
# ---------------------------------------------------------------------------


@dataclass
class _PlanParams:
    needs_retrieval: bool
    retrieval_strategy: str
    needs_pending: bool
    pending_reference: str
    answer_mode: str
    tools: list[str]
    v17_job_type: str
    v17_job: dict[str, Any] | None
    v17_sources: tuple[Any, ...]


_LIGHT_COMPLEX_REASON_CODES = frozenset({
    "decision_tradeoff",
    "multi_dimension",
    "multi_analysis",
    "pro_con",
    "diagnostic_reasoning",
})
_EXPLICIT_GROUNDED_EVIDENCE_HINTS = (
    "知识库",
    "文档",
    "资料",
    "来源",
    "数据",
    "报告",
    "案例",
    "证据",
    "网页",
    "链接",
    "论文",
)


def _should_prefer_light_complex(
    *,
    message: str,
    http_use_knowledge: bool,
    v13: _V13Result,
) -> bool:
    """Complex 决策题默认保留 complex，但不一律走 KB-heavy knowledge_grounded。"""
    if http_use_knowledge or v13.prepare_intent is not None or v13.commit_intent:
        return False
    msg = (message or "").strip()
    if not msg:
        return False
    if any(token in msg for token in _EXPLICIT_GROUNDED_EVIDENCE_HINTS):
        return False
    signal = evaluate_complex_candidate(msg)
    if not signal.complex_candidate:
        return False
    return bool(set(signal.reason_codes) & _LIGHT_COMPLEX_REASON_CODES)


def _build_plan_params(
    message: str,
    decision: Any,
    xiezuo_pan: Any,
    force_skip: bool,
    v13: _V13Result,
    v11_plan_video_url: str | None,
    http_use_knowledge: bool,
) -> _PlanParams:
    """Determine retrieval/pending/answer/tools from routing + V13 results."""
    _v13_is_video_prepare = (
        v13.prepare_intent is not None
        and getattr(v13.prepare_intent, "source_type", "") in ("local_video", "web_video")
    )
    _prefer_light_complex = _should_prefer_light_complex(
        message=message,
        http_use_knowledge=http_use_knowledge,
        v13=v13,
    )

    _needs_retrieval = bool(
        decision.need_rag and xiezuo_pan.allow_kb and not force_skip
    )
    if _prefer_light_complex:
        _needs_retrieval = False
    _needs_pending = bool(v13.prepare_intent is not None or v13.commit_intent)

    if v13.commit_intent:
        _pending_reference = "commit"
    elif v13.prepare_intent is not None:
        _pending_reference = "prepare"
    else:
        _pending_reference = "none"

    if v13.commit_intent:
        _answer_mode = "commit_result"
    elif v13.prepare_intent is not None:
        _answer_mode = "temporary_material"
    elif _needs_retrieval:
        _answer_mode = "knowledge_grounded"
    else:
        _answer_mode = "direct"

    _tools: list[str] = []
    if _needs_retrieval:
        _tools.append("retrieve_knowledge")
    if xiezuo_pan.allow_web:
        _tools.append("fetch_web")
    if v13.prepare_intent is not None:
        src = getattr(v13.prepare_intent, "source_type", "")
        # 工具名必须与下游门禁一致：text_file 在 pending_flow / early_document
        # 里都按 "prepare_file" 校验（见 material_policy.is_tool_allowed）。
        if src == "text_file":
            _tools.append("prepare_file")
        else:
            _tools.append(f"prepare_{src}" if src else "prepare_text")
    if v13.commit_intent:
        _tools.append("commit_pending")
    if v11_plan_video_url or _v13_is_video_prepare:
        _tools.append("mcp_video_to_text")
    if v11_plan_video_url:
        _tools.append("prepare_web_video")

    # V17 audit/multi-source override
    _v17_audit_job = build_tool_audit_job(message)
    _v17_sources = extract_url_sources(message)
    _v17_job = None
    _v17_job_type = "normal_chat"

    if _v17_audit_job is not None:
        _v17_job = _v17_audit_job
        _v17_job_type = "tool_audit"
        _tools = list(_v17_job["tool_plan"].get("tools_allowed") or [])
        _answer_mode = "source_brief_summary"
    elif len(_v17_sources) >= 2 and any(
        kw in (message or "") for kw in ("对比", "比较", "不同", "角度", "优点", "局限", "compare")
    ):
        _v17_job = build_analysis_job(message, _v17_sources)
        _v17_job_type = "multi_source_compare"
        _tools = list(_v17_job["tool_plan"].get("tools_allowed") or [])
        _answer_mode = "source_brief_summary"

    return _PlanParams(
        needs_retrieval=_needs_retrieval,
        retrieval_strategy="auto",
        needs_pending=_needs_pending,
        pending_reference=_pending_reference,
        answer_mode=_answer_mode,
        tools=_tools,
        v17_job_type=_v17_job_type,
        v17_job=_v17_job,
        v17_sources=tuple(_v17_sources) if _v17_job else (),
    )


# ---------------------------------------------------------------------------
# Main orchestrator (now ~80 lines)
# ---------------------------------------------------------------------------


def run_main_invoke_executor(rt: Any, frame: AgentRunFrame) -> AgnoCollaborationPlan:
    """执行 Main 主链：路由判断 → V13 分类 → Plan 组装。"""
    inputs: dict[str, Any] = dict(frame.inputs)
    message = str(inputs.get("message", ""))
    http_use_knowledge = bool(inputs.get("http_use_knowledge", False))
    history: SessionHistorySnapshot | None = inputs.get("history")
    intent_classifier = inputs.get("intent_classifier")
    msg = message.strip()
    has_explicit_web = agno_web_service.user_requests_web_search(msg)

    task_id = issue_task_id()

    # --- Stage 1: routing decisions ---
    intent = rt.shibie_yitu(
        message=message, http_use_knowledge=http_use_knowledge,
        has_explicit_web=has_explicit_web, history=history,
        intent_classifier=intent_classifier,
    )
    followup_video = (
        history.followup_video_anchor(message) if history is not None else None
    )
    web_mode, comp = rt.pan_jubu_celue(
        intent=intent, http_use_knowledge=http_use_knowledge,
        has_explicit_web=has_explicit_web,
    )
    xiezuo_pan = rt.pan_zhuyao_panjue(
        intent=intent, http_use_knowledge=http_use_knowledge,
        has_explicit_web=has_explicit_web, comp=comp, web_mode=web_mode,
    )
    decision = rt.panduan_main_decision(
        task_id=task_id, intent=intent,
        http_use_knowledge=http_use_knowledge, has_explicit_web=has_explicit_web,
    )
    force_skip = rt.pan_shibai_bianjie(
        intent=intent, xiezuo_pan=xiezuo_pan,
        http_use_knowledge=http_use_knowledge, has_explicit_web=has_explicit_web,
    )
    if force_skip:
        web_mode = "explicit_only"

    # Followup video trace
    if followup_video is not None:
        extra_explain = (
            f"v8:main:history_used=true followup_video={followup_video.source_id}"
        )
        new_explain = (
            (decision.routing_explain or "").strip() + "\uff1b" + extra_explain
        ).strip("\uff1b")
        decision = decision.model_copy(update={"routing_explain": new_explain})

    # V10/V11 trace fields
    v10_signal = rt._last_router_signal or "explicit"
    v10_llm_intent = rt._last_llm_intent or "(skipped)"
    v10_llm_error = rt._last_llm_error or "(none)"
    v10_fb_reason = rt._last_fallback_reason or "(none)"
    v11_explicit_kind = rt._last_explicit_kind or "(none)"
    v11_video_url = rt._last_video_url or "(none)"
    v10_trace = (
        f"v10:router_signal={v10_signal} "
        f"v10:llm_intent={v10_llm_intent} "
        f"v10:llm_error={v10_llm_error} "
        f"v10:fallback_reason={v10_fb_reason} "
        f"v10:explicit_kind={v11_explicit_kind} "
        f"v11:video_url={v11_video_url}"
    )
    new_explain = (
        (decision.routing_explain or "").strip() + "\uff1b" + v10_trace
    ).strip("\uff1b")
    decision = decision.model_copy(update={"routing_explain": new_explain})

    v11_plan_video_url = (rt._last_video_url or "").strip() or None

    # --- Stage 2: V13 classification ---
    v13 = _classify_v13(msg, inputs)

    # --- Stage 3: plan parameters ---
    pp = _build_plan_params(
        message,
        decision,
        xiezuo_pan,
        force_skip,
        v13,
        v11_plan_video_url,
        http_use_knowledge,
    )

    _v13_is_video_prepare = (
        v13.prepare_intent is not None
        and getattr(v13.prepare_intent, "source_type", "") in ("local_video", "web_video")
    )

    # --- Stage 4: assemble plan ---
    execution_agents: list[ExecutionAgentSpec] = [
        ExecutionAgentSpec(name="memory", timeout_ms=500, required=False),
    ]
    if pp.needs_retrieval:
        execution_agents.append(ExecutionAgentSpec(name="kb", timeout_ms=3000, required=False))
    if "fetch_web" in tuple(pp.tools):
        execution_agents.append(ExecutionAgentSpec(name="web", timeout_ms=5000, required=False))
    if v11_plan_video_url or _v13_is_video_prepare or pp.v17_job_type == "multi_source_compare":
        execution_agents.append(
            ExecutionAgentSpec(
                name="video",
                timeout_ms=10000,
                required=bool(v11_plan_video_url or _v13_is_video_prepare),
            ),
        )
    if (
        v13.prepare_intent is not None
        and getattr(v13.prepare_intent, "source_type", "") in ("text_file", "web_url")
    ):
        execution_agents.append(
            ExecutionAgentSpec(name="document", timeout_ms=6000, required=False),
        )

    plan = AgnoCollaborationPlan(
        decision=decision,
        force_skip_evidence=force_skip,
        web_supplement_mode=web_mode,
        answer_composition=comp,
        xiezuo_pan=xiezuo_pan,
        video_url=None if _v13_is_video_prepare else v11_plan_video_url,
        v13_prepare_intent=v13.prepare_intent,
        v13_commit_intent=v13.commit_intent,
        needs_retrieval=pp.needs_retrieval,
        retrieval_strategy=pp.retrieval_strategy,
        needs_pending=pp.needs_pending,
        pending_reference=pp.pending_reference,
        answer_mode=pp.answer_mode,
        tools_allowed=tuple(pp.tools),
        job_type=pp.v17_job_type,
        source_inputs=pp.v17_sources,
        tool_plan=pp.v17_job["tool_plan"] if pp.v17_job else None,
        analysis_job=pp.v17_job,
        fallback_steps=tuple((pp.v17_job or {}).get("tool_plan", {}).get("fallback_steps", []) or []),
        tools_disabled=tuple((pp.v17_job or {}).get("tool_plan", {}).get("tools_disabled", []) or []),
        privacy_scope=str((pp.v17_job or {}).get("tool_plan", {}).get("privacy_scope", "") or ""),
        budget_policy=dict((pp.v17_job or {}).get("tool_plan", {}).get("budget_policy", {}) or {}),
        max_rounds=int((pp.v17_job or {}).get("tool_plan", {}).get("max_rounds", 0) or 0),
        original_user_intent=message,
        execution_plan=ExecutionPlan(
            deadline_ms=20_000,
            answer_policy="answer_or_partial_within_deadline",
            agents=tuple(execution_agents),
            fallback="background_task_if_timeout",
        ),
    )
    plan = rt.qingxi_yueshu_doudi(plan)

    # --- Trace ---
    v8_history_used = followup_video is not None
    trace(
        f"MainAgentRuntime exec frame={frame.frame_id} intent={intent} "
        f"renwu={plan.xiezuo_pan.renwu_lei} allow_kb={plan.xiezuo_pan.allow_kb} "
        f"allow_web={plan.xiezuo_pan.allow_web} force_skip={force_skip} "
        f"router_source={decision.router_source} "
        f"v8_history_used={v8_history_used} "
        f"v8_followup_video={followup_video.source_id if followup_video else None} "
        f"v10_router_signal={v10_signal} v10_llm_intent={v10_llm_intent} "
        f"v10_llm_error={v10_llm_error} v10_fallback_reason={v10_fb_reason} "
        f"v10_explicit_kind={v11_explicit_kind} v11_video_url={v11_video_url} "
        f"v13_llm_signal={v13.llm_signal} "
        f"v13_prepare={plan.v13_prepare_intent.source_type if plan.v13_prepare_intent else None} "
        f"v13_commit={plan.v13_commit_intent} "
        f"role_sig={frame.role_signature}"
    )
    return plan


__all__ = ["run_main_invoke_executor"]
