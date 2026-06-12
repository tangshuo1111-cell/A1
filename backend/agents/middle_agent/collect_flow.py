"""
middle_agent 旧主链 `collect()` 路径所需逻辑。

> 注：本文件 **不是** V6 主入口。仅承接旧主链 `workflow.chat_graph` 与既有
> `test_middle_agent.py` 用到的 `collect()` 实现（RAG / Tool / MCP 多路取材）。
> 新代码请只走 `MiddleAgent.caipan` + `gather_agno_materials`。

执行链见 `collect_flow_execute.py`，证据包评估见 `collect_flow_eval.py`。
"""

from __future__ import annotations

from agents.middle_agent import collect_flow_eval as _cfe
from agents.middle_agent import collect_flow_execute as _cfx
from agents.shared.evidence_normalizer import normalize_evidence_lists
from debug_trace import trace
from observability import log_phase
from schemas import CollectionTask, EvidencePack
from services.capabilities.knowledge.retrieve_service import count_kb_chunks
from tools.policy.selection import plan_collection_steps


def collect(task: CollectionTask) -> EvidencePack:
    """分阶段：A) 各渠道原始片段；B) normalize；C) evaluate；D) retrieval_debug。"""
    evidence_chunks: list[str] = []
    sources: list[str] = []
    tool_http_ok_box = [False]
    hint_read_ok_box = [False]
    refine_attempted = False
    tr: list[str] = []
    kb_n = count_kb_chunks()
    tr.append(f"kb_chunk_count={kb_n}")

    order, policy_notes = plan_collection_steps(task)
    tr.extend(policy_notes)
    tr.append(f"priority_order={','.join(order)}")
    trace(
        f"middle_agent.collect start task_id={task.task_id} "
        f"channels={task.available_channels} order={order}"
    )
    log_phase(
        task.task_id,
        "middle_collect_start",
        f"channels={task.available_channels} order={','.join(order)}",
    )

    for step in order:
        ec, ss, sub = _cfx._run_step(
            task,
            step,
            tool_http_ok_holder=tool_http_ok_box,
            hint_ok_holder=hint_read_ok_box,
        )
        tr.extend(sub)
        evidence_chunks.extend(ec)
        sources.extend(ss)
    tr.append("primary_wave_done")

    if (
        "rag" in task.available_channels
        and sum(1 for s in sources if s == "rag") == 0
        and task.search_query.strip()
    ):
        widen_q = (
            (task.rag_search_queries[0] if task.rag_search_queries else "")
            or task.search_query.strip()
        )
        tr.append("rag_refine_wide_topk")
        trace(f"middle_agent -> refine RAG widen top_k q={widen_q[:48]!r}")
        rc, rs, rst = _cfx._run_rag(task, query=widen_q.strip(), top_k=14)
        tr.extend(rst)
        evidence_chunks.extend(rc)
        sources.extend(rs)
        refine_attempted = True

    ne, src_al, norm_tr = normalize_evidence_lists(evidence_chunks, sources)
    tr.extend(norm_tr)
    tr.append(f"normalize_pre n={len(ne)}")
    pack_pre = _cfe._evaluate_pack(
        task,
        ne,
        src_al,
        tool_http_ok=tool_http_ok_box[0],
        hint_read_ok=hint_read_ok_box[0],
        refine_attempted=refine_attempted,
        collection_trace=tr + ["eval_pre"],
        secondary_channel_attempted="",
    )

    secondary_attempted = ""
    if _cfe._needs_secondary_wave(pack_pre):
        sec = _cfe._pick_secondary_step(
            task, src_al, refine_attempted=refine_attempted
        )
        if sec:
            tr.append(f"secondary_wave={sec}")
            trace(f"middle_agent -> secondary single step={sec}")
            ec, ss, sub = _cfx._run_step(
                task,
                sec,
                tool_http_ok_holder=tool_http_ok_box,
                hint_ok_holder=hint_read_ok_box,
            )
            tr.extend(sub)
            evidence_chunks.extend(ec)
            sources.extend(ss)
            secondary_attempted = sec
        else:
            tr.append("secondary_wave=skipped_no_eligible")

    ne, src_al, norm_tr2 = normalize_evidence_lists(evidence_chunks, sources)
    tr.extend(norm_tr2)
    tr.append(f"normalize_final n={len(ne)}")
    final = _cfe._evaluate_pack(
        task,
        ne,
        src_al,
        tool_http_ok=tool_http_ok_box[0],
        hint_read_ok=hint_read_ok_box[0],
        refine_attempted=refine_attempted,
        collection_trace=tr + ["eval_final"],
        secondary_channel_attempted=secondary_attempted,
    )

    rag_hit_n = sum(1 for s in src_al if s == "rag")
    web_hit_n = sum(1 for s in src_al if s == "web_search")
    rd: dict[str, object] = {
        "kb_chunk_count": kb_n,
        "rag_queries_planned": list(task.rag_search_queries or [task.search_query]),
        "rag_hit_chunks": rag_hit_n,
        "web_search_planned": "search" in order,
        "web_search_hit_chunks": web_hit_n,
        "trace_tail": tr[-14:],
    }
    if kb_n == 0:
        rd["rag_miss_reason"] = "kb_empty_run_bootstrap"
    elif "rag" in task.available_channels and rag_hit_n == 0:
        rd["rag_miss_reason"] = "no_hits_after_variants_and_refine"
    else:
        rd["rag_miss_reason"] = "hits_ok" if rag_hit_n else "rag_channel_off"

    final = final.model_copy(update={"retrieval_debug": rd})

    trace(
        f"middle_agent.collect done task_id={task.task_id} evidence_n={len(final.evidence_list)} "
        f"completeness_ok={final.completeness_ok} need_more={final.need_more_info} "
        f"coverage={final.coverage_score:.2f} secondary={secondary_attempted!r}"
    )
    log_phase(
        task.task_id,
        "middle_collect_done",
        f"ok={final.completeness_ok} cov={final.coverage_score:.2f} n={len(final.evidence_list)}",
    )
    return final
