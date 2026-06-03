"""
轻量可观测：统一 phase 日志行，避免各处格式不一致。
依赖 logging；未 basicConfig 时默认可能不显示 INFO，请用 app.py --log。
"""

from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict
from typing import Any

_log = logging.getLogger("light_maqa")


def log_phase(task_id: str, phase: str, detail: str = "") -> None:
    """
    一行记录：task_id + 阶段名 + 简短说明。
    V4 收口：关键 phase 含 dispatch_done、main_agent_done、middle_collect_*、
    answer_done、workflow_done、context_fetch_failed、knowledge_store_init_failed。
    """
    d = (detail or "").replace("\n", " ").strip()
    if len(d) > 320:
        d = d[:317] + "..."
    _log.info("task_id=%s phase=%s %s", task_id, phase, d)


# --- 进程内指标（与 api / services / tools 共用）---

_metrics_lock = threading.Lock()
_metrics_counts: dict[str, int] = defaultdict(int)
_metrics_retrieval: dict[str, int] = defaultdict(int)
_metrics_nodes: dict[str, int] = defaultdict(int)


def metrics_incr(name: str, n: int = 1) -> None:
    with _metrics_lock:
        _metrics_counts[name] += n


def metrics_record_request(path: str, status_code: int, duration_ms: float) -> None:
    with _metrics_lock:
        _metrics_counts["http_requests_total"] += 1
        _metrics_counts[f"http_status_{status_code}"] += 1
        _metrics_counts[f"http_path_{path[:48]}"] += 1
        _metrics_counts["_latency_sum_ms"] = _metrics_counts.get("_latency_sum_ms", 0) + int(
            duration_ms
        )
        _metrics_counts["_latency_n"] = _metrics_counts.get("_latency_n", 0) + 1


def metrics_record_chat_sync(success: bool) -> None:
    metrics_incr("chat_sync_total")
    metrics_incr("chat_sync_ok" if success else "chat_sync_fail")


def metrics_record_chat_async_submitted() -> None:
    metrics_incr("chat_async_submitted_total")


def metrics_record_task_terminal(status: str) -> None:
    metrics_incr(f"task_terminal_{status}")


def metrics_record_tool_call(name: str, ok: bool) -> None:
    metrics_incr("tool_calls_total")
    metrics_incr(f"tool_{name}_{'ok' if ok else 'fail'}")


def metrics_record_retrieval_mode(mode: str) -> None:
    with _metrics_lock:
        _metrics_retrieval[mode or "unknown"] += 1


def metrics_record_graph_node(node: str) -> None:
    with _metrics_lock:
        _metrics_nodes[node] += 1


def metrics_snapshot() -> dict[str, Any]:
    with _metrics_lock:
        lat_n = _metrics_counts.get("_latency_n", 0) or 1
        lat_avg = _metrics_counts.get("_latency_sum_ms", 0) / lat_n
        ctr = dict(_metrics_counts)
        ctr.pop("_latency_sum_ms", None)
        ctr.pop("_latency_n", None)
        return {
            "counters": ctr,
            "retrieval_modes": dict(_metrics_retrieval),
            "graph_nodes": dict(_metrics_nodes),
            "http_latency_avg_ms": round(lat_avg, 2),
        }


class MetricsTimer:
    def __init__(self) -> None:
        self._t0 = time.perf_counter()

    def elapsed_ms(self) -> float:
        return (time.perf_counter() - self._t0) * 1000


def enrich_turn_extra(
    extra: dict[str, Any],
    *,
    main_plan_call_count: int = 1,
    kb_retrieve_call_count: int = 0,
) -> dict[str, Any]:
    """Attach §12 turn-level counters into chat extra (also bumps process metrics)."""
    out = dict(extra)
    timings = dict(out.get("agent_timings") or {})
    timings["main_plan_call_count"] = max(0, int(main_plan_call_count))
    timings["kb_retrieve_call_count"] = max(0, int(kb_retrieve_call_count))
    out["agent_timings"] = timings
    metrics_incr("main_plan_call_count_total", max(0, int(main_plan_call_count)))
    metrics_incr("kb_retrieve_call_count_total", max(0, int(kb_retrieve_call_count)))
    return out
