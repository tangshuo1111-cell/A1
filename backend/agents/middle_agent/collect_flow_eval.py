"""证据包评估与次优渠道选择：关键证据/噪声/缺口、`_evaluate_pack`、`_pick_secondary_step`。"""

from __future__ import annotations

import re
from collections import Counter

from schemas import CollectionTask, EvidencePack
from tools.policy.execution_order import wants_list_files


def _is_mock_evidence(source: str, text: str) -> bool:
    return source == "mock_store" or "[mock]" in text


def _token_overlap(q: str, text: str) -> float:
    tq = set(re.findall(r"[\w\u4e00-\u9fff]+", (q or "").lower()))
    tt = set(re.findall(r"[\w\u4e00-\u9fff]+", (text or "").lower()))
    if not tq:
        return 0.0
    return len(tq & tt) / max(len(tq), 1)


def _derive_key_noise_time(
    task: CollectionTask,
    chunks: list[str],
    srcs: list[str],
) -> tuple[list[str], list[str], str, bool]:
    """关键证据 / 噪声说明 / 时效说明 / 时效是否视为可用（轻规则）。"""
    noise: list[str] = []
    if not chunks:
        return [], [], "无证据，不谈时效", True

    seen_norm: set[str] = set()
    dup_hit = False
    short_hit = False
    for c in chunks:
        norm = re.sub(r"\s+", " ", c.strip()[:100]).lower()
        if norm in seen_norm and norm:
            dup_hit = True
        seen_norm.add(norm)
        if len(c.strip()) < 40:
            short_hit = True
    if dup_hit:
        noise.append("存在重复或高度相似的证据片段，阅读时注意去重")
    if short_hit:
        noise.append("存在过短片段，信息密度可能偏低（可能是噪声或摘要残片）")

    for c, s in zip(chunks, srcs):  # noqa: B905
        low = c.lower()
        if s in ("mcp_sim", "mcp_stdio") and "ping" in low:
            noise.append(
                "MCP 段主要为连通性/握手（stdio 或进程内），不宜当作业务事实证据"
            )
            break

    scored = [
        (_token_overlap(task.search_query, c), i, c)
        for i, c in enumerate(chunks)
    ]
    scored.sort(key=lambda x: (-x[0], x[1]))
    key_out: list[str] = []
    seen_key: set[str] = set()
    for _ov, _i, c in scored:
        kn = re.sub(r"\s+", " ", c.strip()[:160]).lower()
        if kn in seen_key:
            continue
        seen_key.add(kn)
        key_out.append(c)
        if len(key_out) >= 5:
            break

    uniq = set(srcs)
    if "web_search" in uniq:
        noise.append("Web 检索为摘要级，请点开来源链接核对事实")
    if uniq == {"mcp_sim"}:
        return key_out, noise, "仅 MCP 模拟握手，无时间维度与事实正文", False
    if "rag" in uniq:
        note = "知识库片段通常未标注撰写/更新时间，请自行判断时效"
        return key_out, noise, note, True
    if "tool_url" in uniq:
        return key_out, noise, "网页抓取未自动解析发布日期，时效需结合来源核对", True
    if "tool_file" in uniq:
        return key_out, noise, "本地文件未自动读取修改时间到证据包，时效需自行核对", True
    return key_out, noise, "未做统一时效校验，请结合来源自行判断", True


def _pick_secondary_step(
    task: CollectionTask,
    sources: list[str],
    *,
    refine_attempted: bool,
) -> str | None:
    """选一个尚未产出有效数据的次优渠道（单步）。"""
    c = Counter(sources)
    prio = task.middle_collect_priority or "balanced"
    if prio == "rag_first":
        candidates = ["local", "http", "rag"]
    elif prio == "local_first":
        candidates = ["rag", "http", "local"]
    elif prio == "http_first":
        candidates = ["rag", "local", "http"]
    else:
        candidates = ["rag", "local", "http"]

    for step in candidates:
        if step == "rag":
            if "rag" not in task.available_channels:
                continue
            if c["rag"] > 0:
                continue
            if refine_attempted:
                continue
        elif step == "local":
            if not task.enable_local_file_tools:
                continue
            if not (task.local_path_hints or wants_list_files(task.search_query)):
                continue
            if c["tool_file"] > 0:
                continue
        elif step == "http":
            if "tool" not in task.available_channels or not task.link_urls:
                continue
            if c["tool_url"] > 0:
                continue
        else:
            continue
        return step
    return None


def _needs_secondary_wave(pack: EvidencePack) -> bool:
    """仅在完整性未过或仍提示需补资料时触发次优单步（避免无意义重复调用）。"""
    return (not pack.completeness_ok) or pack.need_more_info


def _evaluate_pack(
    task: CollectionTask,
    non_empty: list[str],
    sources: list[str],
    *,
    tool_http_ok: bool,
    hint_read_ok: bool,
    refine_attempted: bool,
    collection_trace: list[str],
    secondary_channel_attempted: str,
) -> EvidencePack:
    n = len(non_empty)
    uniq_sources = sorted(set(sources))
    total_chars = sum(len(x) for x in non_empty)

    gap_notes: list[str] = []
    missing_parts: list[str] = []
    need_more = False
    next_sug = ""

    if n == 0:
        need_more = True
        gap_notes.append("没有任何非空证据片段")
        next_sug = "rag" if "rag" in task.available_channels else "tool_local"
    elif n == 1 and _is_mock_evidence(sources[0] if sources else "", non_empty[0]):
        need_more = True
        gap_notes.append("仅一条占位/mock 级证据，可信度不足")

    rag_hits = sum(1 for s in sources if s == "rag") if "rag" in task.available_channels else 0
    if "rag" in task.available_channels:
        if rag_hits == 0:
            gap_notes.append("知识库检索零命中")
            need_more = True
            next_sug = next_sug or "rag"
        elif rag_hits == 1 and total_chars < 400:
            gap_notes.append("知识库命中偏少/偏短")
            need_more = need_more or task.is_compound

    if task.link_urls and "tool" in task.available_channels and not tool_http_ok:
        missing_parts.append("外部资料未获取成功")
        gap_notes.append("URL 工具未拿到有效正文")

    if task.enable_local_file_tools and task.local_path_hints and not hint_read_ok:
        missing_parts.append("本地文件未读取成功")
        gap_notes.append("本地路径读取失败")

    if task.is_compound and n < 2 and "rag" in task.available_channels:
        gap_notes.append("复合问题但证据条数偏少")
        need_more = True

    cov = 0.0
    if n:
        cov += min(0.5, 0.1 * n)
    if total_chars > 800:
        cov += 0.2
    if len(uniq_sources) >= 2:
        cov += 0.2
    if n and not missing_parts and not any("零命中" in g for g in gap_notes):
        cov += 0.1
    cov = min(1.0, cov)

    missing_info = "；".join(missing_parts) if missing_parts else ""

    key_evidence, noise_notes, time_validity_note, time_validity_ok = _derive_key_noise_time(
        task, non_empty, sources
    )

    completeness_ok = n > 0
    if missing_parts:
        completeness_ok = False
    if "rag" in task.available_channels and rag_hits == 0:
        completeness_ok = False

    gap_categories: list[str] = []
    if n == 0:
        gap_categories.append("empty_evidence")
    elif n == 1 and sources and _is_mock_evidence(sources[0], non_empty[0]):
        gap_categories.append("mock_or_placeholder")
    if "rag" in task.available_channels:
        if rag_hits == 0:
            gap_categories.append("zero_rag_hit")
        elif rag_hits == 1 and total_chars < 400:
            gap_categories.append("thin_rag_hit")
    if task.link_urls and "tool" in task.available_channels and not tool_http_ok:
        gap_categories.append("url_tool_failed")
    if task.enable_local_file_tools and task.local_path_hints and not hint_read_ok:
        gap_categories.append("local_file_failed")
    if task.is_compound and n < 2 and "rag" in task.available_channels:
        gap_categories.append("compound_thin")
    if not time_validity_ok:
        gap_categories.append("time_uncertain")
    if need_more and n > 0 and completeness_ok:
        gap_categories.append("depth_or_coverage_insufficient")

    if n == 0:
        evidence_state = "not_found"
    elif missing_parts:
        evidence_state = "channel_failed"
    elif not time_validity_ok:
        evidence_state = "stale_or_unverified"
    elif (not completeness_ok) or need_more:
        evidence_state = "weak_hit"
    else:
        evidence_state = "ok"

    next_best = next_sug or (
        "rag"
        if "rag" in task.available_channels
        else ("tool_local" if task.enable_local_file_tools else "tool_url")
    )

    summary_bits: list[str] = []
    if (task.routing_brief or "").strip():
        summary_bits.append("路由摘要：" + task.routing_brief[:160])
    if task.collection_goal:
        summary_bits.append(task.collection_goal[:200])
    if non_empty:
        summary_bits.append(
            f"共 {n} 条证据，约 {total_chars} 字；渠道 {','.join(uniq_sources)}；"
            f"覆盖自评 {cov:.2f}"
        )
    else:
        summary_bits.append("未获得有效证据片段。")
    if gap_notes:
        summary_bits.append("缺口：" + " | ".join(gap_notes[:4]))
    if noise_notes:
        summary_bits.append("噪声评估：" + " | ".join(noise_notes[:3]))
    if key_evidence:
        summary_bits.append(f"关键证据 {len(key_evidence)} 条（按与问句词重叠优先）")
    summary_bits.append(f"时效：{time_validity_note}")
    summary_bits.append(
        f"资料状态={evidence_state}；缺口标签={','.join(gap_categories) or '无'}；"
        f"下一优先渠道={next_best}"
    )
    if collection_trace:
        summary_bits.append("轨迹：" + " -> ".join(collection_trace[-5:]))

    evidence_summary = " ".join(summary_bits).strip()

    parts_why: list[str] = []
    if (not completeness_ok) or need_more:
        parts_why = list(gap_notes)
        if missing_info:
            parts_why.append(missing_info)
        if secondary_channel_attempted:
            parts_why.append(f"已尝试次优渠道={secondary_channel_attempted}仍不足")
    why_detail = "；".join(parts_why[:8]) if parts_why else (
        "证据与渠道自评可接受。" if evidence_state == "ok" else "资料仍不足，原因未分类"
    )
    gc_str = ",".join(gap_categories) if gap_categories else "无"
    why = f"【资料状态】{evidence_state} | 【缺口分类】{gc_str} | 【说明】{why_detail}"

    return EvidencePack(
        task_id=task.task_id,
        source_list=sources,
        evidence_list=non_empty,
        key_evidence_list=key_evidence,
        noise_notes=noise_notes,
        evidence_summary=evidence_summary or "（middle）证据摘要",
        completeness_ok=completeness_ok,
        time_validity_ok=time_validity_ok,
        time_validity_note=time_validity_note,
        missing_info=missing_info,
        need_more_info=need_more,
        coverage_score=cov,
        gap_notes=gap_notes,
        next_channel_suggestion=next_best,
        next_best_channel=next_best,
        refine_attempted=refine_attempted,
        collection_trace=list(collection_trace),
        secondary_channel_attempted=secondary_channel_attempted,
        why_still_insufficient=why,
        evidence_state=evidence_state,
        gap_categories=gap_categories,
        retrieval_debug={},
    )
