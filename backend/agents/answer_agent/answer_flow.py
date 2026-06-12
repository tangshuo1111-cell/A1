"""
answer_agent 旧主链 `answer()` 路径所需逻辑。

> 注：本文件 **不是** V6 主入口。仅承接旧主链 `workflow.chat_graph` 与既有
> `test_answer_agent_output.py` 用到的 `answer()` 实现（KB / direct / external 模板组装）。
> 新代码请只走 `AnswerAgent.huida` / `AnswerAgent.pan`。

直接/外链分支见 `answer_flow_direct.py`，正文拼装见 `answer_flow_compose.py`。
"""

from __future__ import annotations

from debug_trace import trace
from schemas import AnswerResult, EvidencePack, MainDecision

from . import answer_flow_compose as _compose
from . import answer_flow_direct as _direct


def answer(
    user_query: str,
    evidence: EvidencePack,
    *,
    decision: MainDecision | None = None,
    context_snippet: str = "",
    channels_used: list[str] | None = None,
) -> AnswerResult:
    """旧主链回答主入口（chat_graph 用）。新代码请用 `AnswerAgent.huida`。"""
    dec = decision or MainDecision(
        task_id=evidence.task_id,
        need_rag=True,
        answer_channel="kb",
        router_source="rules",
    )
    channel = (dec.answer_channel or "kb").strip().lower()

    if channel == "direct":
        return _direct._answer_direct(
            user_query,
            evidence,
            decision=dec,
            context_snippet=context_snippet,
            channels_used=channels_used,
        )

    ext = _direct._answer_external_insufficient(
        user_query,
        evidence,
        decision=dec,
        channels_used=channels_used,
    )
    if ext is not None:
        return ext

    q = user_query.strip()
    style = (dec.answer_style if dec else "general") or "general"
    primary = (dec.primary_goal if dec else "") or q[:120]
    _ = (dec.answer_style_hint if dec else "") or ""

    basis = _compose._pick_basis(evidence)
    has_evidence = bool(basis)
    insufficient = (
        (not evidence.completeness_ok)
        or bool((evidence.missing_info or "").strip())
        or not has_evidence
    )

    chans = list(channels_used or [])
    gaps = list(evidence.gap_categories or [])
    src = list(evidence.source_list or [])

    if "tool_local" in chans and "local_file_failed" in gaps:
        trace(f"answer_agent.tool_local_failed task_id={evidence.task_id}")
        fail_body = _direct._strip_answer_leaks(_compose._compose_tool_local_failure())
        return AnswerResult(
            task_id=evidence.task_id,
            final_answer=fail_body,
            answer_type="insufficient",
            has_insufficient_info_notice=True,
            suggest_more_retrieval=False,
            should_save_history=True,
            task_status="partial",
            user_visible_status="示例文件读取失败",
            channels_used=chans,
            router_source=(dec.router_source if dec else ""),
            evidence_state=evidence.evidence_state or "",
        )

    trace(
        f"answer_agent.answer task_id={evidence.task_id} style={style} "
        f"has_evidence={has_evidence} insufficient={insufficient} "
        f"evidence_state={evidence.evidence_state} channel={channel}"
    )

    coverage_low = bool(
        evidence.coverage_score and evidence.coverage_score < 0.35 and has_evidence
    )
    time_note = (evidence.time_validity_note or "").strip()

    if (
        channel == "kb"
        and "tool_local" in chans
        and "tool_file" in src
        and has_evidence
        and not insufficient
    ):
        had_rag = "rag" in chans
        body = _compose._compose_tool_forward_answer(
            basis=basis,
            style=style,
            had_rag=had_rag,
            time_note=time_note,
            coverage_low=coverage_low,
            context_snippet=context_snippet,
        )
        final_answer = _direct._strip_answer_leaks(body)
        trace(
            f"answer_agent.tool_forward task_id={evidence.task_id} had_rag={had_rag}"
        )
        return AnswerResult(
            task_id=evidence.task_id,
            final_answer=final_answer,
            answer_type=_direct._map_answer_type(style, False),
            has_insufficient_info_notice=False,
            suggest_more_retrieval=bool(evidence.need_more_info),
            should_save_history=True,
            task_status="succeeded",
            user_visible_status="",
            channels_used=chans,
            router_source=(dec.router_source if dec else ""),
            evidence_state=evidence.evidence_state or "",
        )

    if (
        channel == "external"
        and "web_search" in chans
        and has_evidence
        and not insufficient
    ):
        body = _compose._compose_web_search_answer(
            basis=basis,
            style=style,
            time_note=time_note,
            coverage_low=coverage_low,
            context_snippet=context_snippet,
        )
        final_answer = _direct._strip_answer_leaks(body)
        trace(f"answer_agent.web_search_forward task_id={evidence.task_id}")
        return AnswerResult(
            task_id=evidence.task_id,
            final_answer=final_answer,
            answer_type=_direct._map_answer_type(style, False),
            has_insufficient_info_notice=False,
            suggest_more_retrieval=bool(evidence.need_more_info),
            should_save_history=True,
            task_status="succeeded",
            user_visible_status="",
            channels_used=chans,
            router_source=(dec.router_source if dec else ""),
            evidence_state=evidence.evidence_state or "",
        )

    body = _compose._compose_kb_style_answer(
        user_query=q,
        primary=primary,
        style=style,
        channel=channel,
        insufficient=insufficient,
        has_evidence=has_evidence,
        basis=basis,
        time_note=time_note,
        coverage_low=coverage_low,
        context_snippet=context_snippet,
    )
    final_answer = _direct._strip_answer_leaks(body)

    ans_type = _direct._map_answer_type(style, insufficient)
    task_stat = "partial" if insufficient else "succeeded"
    user_vis = (
        "知识库未命中相关片段"
        if insufficient and channel == "kb" and "local_file_failed" not in gaps
        else (
            "覆盖度偏低，仅供参考"
            if coverage_low
            else ""
        )
    )

    rs = (dec.router_source if dec else "") or ""
    return AnswerResult(
        task_id=evidence.task_id,
        final_answer=final_answer,
        answer_type=ans_type,
        has_insufficient_info_notice=insufficient,
        suggest_more_retrieval=evidence.need_more_info or insufficient,
        should_save_history=True,
        task_status=task_stat,
        user_visible_status=user_vis,
        channels_used=chans,
        router_source=rs,
        evidence_state=evidence.evidence_state or "",
    )
