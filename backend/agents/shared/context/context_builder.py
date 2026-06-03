"""
短期上下文：会话压缩记忆 + 最近 N 轮对话（token overlap 筛选、截断）。
非长期向量记忆；session_memory 为轨迹摘要行追加表。
"""

from __future__ import annotations

import re
from typing import Any

from config.settings import settings
from debug_trace import trace
from schemas import TaskInput
from storage import conversation_store, session_memory_store


def _tokens(s: str) -> set[str]:
    return set(re.findall(r"[\w\u4e00-\u9fff]+", (s or "").lower()))


def _overlap_score(query: str, user_turn: str) -> float:
    tq, tu = _tokens(query), _tokens(user_turn)
    if not tq:
        return 0.0
    return len(tq & tu) / max(len(tq), 1)


def _assistant_useful(answer: str, task_status: str | None) -> bool:
    a = (answer or "").strip()
    if len(a) < settings.context_min_assistant_chars:
        return False
    if task_status in ("failed",) and any(
        x in a for x in ("失败", "异常", "error", "failed")
    ):
        return False
    if a.startswith("回答生成失败") or (  # noqa: SIM103
        a.startswith("（骨架") and len(a) < 40
    ):
        return False
    return True


def build_for_task(
    task: TaskInput,
    *,
    turn_limit: int | None = None,
    user_max_chars: int | None = None,
    assistant_max_chars: int | None = None,
) -> tuple[str, dict[str, Any]]:
    lim = turn_limit if turn_limit is not None else settings.context_turn_limit
    u_cap = user_max_chars if user_max_chars is not None else settings.context_user_max_chars
    a_cap = (
        assistant_max_chars
        if assistant_max_chars is not None
        else settings.context_assistant_max_chars
    )

    meta: dict[str, Any] = {
        "context_hit": False,
        "context_hit_count": 0,
        "rounds_loaded": 0,
        "rounds_fetched": 0,
        "turns_skipped": 0,
        "turn_limit": lim,
        "user_max_chars": u_cap,
        "assistant_max_chars": a_cap,
        "relevance_filtered": False,
        "relevance_avg_score": 0.0,
        "context_format": "short_term_v5_memory",
        "context_selected_turns": [],
        "context_reason": "",
        "session_memory_chars": 0,
    }

    if not task.session_id:
        meta["context_reason"] = "未提供 session_id，不读取历史轮次。"
        trace("context_builder: 无 session_id，跳过")
        return "", meta

    mem_txt = session_memory_store.load_recent_text(task.session_id)
    mem_prefix = ""
    if mem_txt.strip():
        mem_prefix = "[会话压缩记忆 | 最近轨迹摘要]\n" + mem_txt.strip() + "\n\n"
        meta["session_memory_chars"] = len(mem_txt.strip())

    mult = max(1, settings.context_fetch_multiplier)
    fetch_cap = min(max(lim * mult, lim), 40)

    try:
        all_rows = conversation_store.load_recent_for_session(
            task.session_id, limit=fetch_cap
        )
    except Exception as e:  # noqa: BLE001
        trace(f"context_builder: 读取会话失败 {e!s}")
        meta["error"] = str(e)
        meta["context_reason"] = f"读取会话失败，未注入上下文：{e!s}"
        return (mem_prefix.rstrip() if mem_prefix else ""), meta

    if not all_rows:
        trace(f"context_builder: session={task.session_id} 无历史")
        meta["context_reason"] = "session 存在但尚无历史轮次（可能是本会话首问）。"
        if mem_prefix:
            meta["context_hit"] = True
            return mem_prefix.rstrip(), meta
        return "", meta

    meta["rounds_fetched"] = len(all_rows)
    q_for_score = (task.clean_query or task.user_query or "").strip()
    selected_turns: list[dict[str, Any]] = []
    rows = all_rows
    n_all = len(all_rows)

    if len(all_rows) > lim:
        n = len(all_rows)
        keep_eff = min(max(0, settings.context_always_keep_last), lim)
        recent_idx = set(range(n - keep_eff, n)) if keep_eff else set()
        slots = lim - len(recent_idx)
        pool_idx = [i for i in range(n) if i not in recent_idx]
        def _pair(i: int) -> tuple[float, int]:
            uq = all_rows[i].get("user_query") or ""
            return (_overlap_score(q_for_score, uq), i)

        scored = sorted((_pair(i) for i in pool_idx), reverse=True)
        picked: set[int] = set(recent_idx)
        scores_taken: list[float] = []
        index_to_score: dict[int, float] = {}
        for sc, i in scored[: max(0, slots)]:
            picked.add(i)
            scores_taken.append(sc)
            index_to_score[i] = sc
        for i in range(n):
            if len(picked) >= lim:
                break
            if i not in picked:
                picked.add(i)
        sel_i = sorted(picked)[:lim]
        rows = [all_rows[i] for i in sel_i]
        meta["relevance_filtered"] = True
        meta["relevance_avg_score"] = (
            sum(scores_taken) / len(scores_taken) if scores_taken else 0.0
        )
        dropped = [i for i in range(n) if i not in set(sel_i)]
        for i in sel_i:
            tid = (all_rows[i].get("task_id") or "")[:12]
            if i in recent_idx:
                reason, score = "keep_recent", None
            elif i in index_to_score:
                reason, score = "relevance_pick", round(index_to_score[i], 4)
            else:
                reason, score = "fill_to_limit", None
            selected_turns.append(
                {"index_in_fetch": i, "task_id": tid, "reason": reason, "overlap": score}
            )
        meta["context_reason"] = (
            f"从最近拉取的 {n_all} 轮中选出 {len(rows)} 轮："
            f"强制保留最近 {keep_eff} 轮；"
            f"词重叠取 {len(scores_taken)} 轮（avg={meta['relevance_avg_score']:.3f}）；"
            f"其余 {len(dropped)} 轮未纳入。"
        )
        trace(
            f"context_builder: relevance pick n_in={n} n_out={len(rows)} "
            f"avg_overlap={meta['relevance_avg_score']:.3f}"
        )
    else:
        for i, r in enumerate(all_rows):
            selected_turns.append(
                {
                    "index_in_fetch": i,
                    "task_id": (r.get("task_id") or "")[:12],
                    "reason": "all_kept_under_limit",
                    "overlap": round(_overlap_score(q_for_score, r.get("user_query") or ""), 4),
                }
            )
        meta["context_reason"] = (
            f"会话内仅 {len(rows)} 轮，未超过上限 {lim}，全部纳入。"
        )

    meta["context_selected_turns"] = selected_turns
    meta["context_hit_count"] = len(rows)

    parts: list[str] = []
    skipped = 0
    for r in rows:
        u = (r.get("user_query") or "").strip()
        a = (r.get("answer") or "").strip()
        st = (r.get("task_status") or "").strip() or None
        uv = (r.get("user_visible_status") or "").strip()
        u_line = f"用户: {u[:u_cap]}"
        if uv and len(uv) <= 100:
            u_line += f" （上轮状态: {uv}）"
        parts.append(u_line)
        if _assistant_useful(a, st):
            parts.append(f"助手: {a[:a_cap]}")
        else:
            skipped += 1
            parts.append("助手: （上轮回复过短或失败，已省略正文）")

    body = "\n".join(parts)
    text = mem_prefix + "[短期会话上下文 | 非长期记忆 | 按时间顺序]\n" + body
    max_total = min(8000, lim * (u_cap + a_cap + 40) + 80)
    if len(text) > max_total:
        text = text[-max_total:]
        meta["context_reason"] += " 正文尾部因总长度上限被截断。"

    meta["context_hit"] = True
    meta["rounds_loaded"] = len(rows)
    meta["turns_skipped"] = skipped
    trace(
        f"context_builder: hit=True hit_count={meta['context_hit_count']} "
        f"skipped_assistant={skipped} len={len(text)}"
    )
    return text, meta
