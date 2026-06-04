"""产品指标 v1 聚合（代理口径）— 供 scripts 与测试共用。"""

from __future__ import annotations

from collections import Counter
from typing import Any

from application.chat.complexity_policy import is_complex_task_scope


def row_from_pg(record: dict[str, Any]) -> dict[str, Any]:
    """PG turn_product_metrics 行 → 与 JSONL/chat 响应兼容的 dict。"""
    return {
        "task_id": record.get("task_id"),
        "task_status": record.get("task_status"),
        "extra": {
            "mode": record.get("mode"),
            "executor_profile": record.get("executor_profile"),
            "is_complex_task": record.get("is_complex_task"),
            "quality_gate_passed": record.get("quality_gate_passed"),
            "insufficient_evidence": record.get("insufficient_evidence"),
            "v15_retrieved_chunks_count": record.get("retrieved_chunks_count"),
            "v15_temporary_materials_count": record.get("temporary_materials_count"),
            "failure_reason_code": record.get("failure_reason_code"),
            "timing_total_ms": record.get("timing_total_ms"),
            "answer_char_count": record.get("answer_char_count"),
        },
    }


def is_complex_task(extra: dict[str, Any], top: dict[str, Any] | None = None) -> bool:
    top = top or {}
    if extra.get("is_complex_task") is True:
        return True
    return is_complex_task_scope(
        mode=str(extra.get("mode") or top.get("mode") or ""),
        executor_profile=str(extra.get("executor_profile") or ""),
        pending_kind=str(extra.get("pending_kind") or "") or None,
        primary_path=str(extra.get("primary_path") or top.get("primary_path") or ""),
        complex_candidate=bool(extra.get("complex_candidate")),
        complex_reason_codes=tuple(extra.get("complex_reason_codes") or ()),
    )


def is_async_task(extra: dict[str, Any]) -> bool:
    profile = str(extra.get("executor_profile") or "").lower()
    pending = str(extra.get("pending_kind") or "").lower()
    return profile == "async" or pending == "escalate_to_async"


def is_done_status(raw: str) -> bool:
    return str(raw or "").lower() in {"done", "succeeded"}


def is_effective_complete(extra: dict[str, Any], top: dict[str, Any]) -> bool:
    status = str(top.get("task_status") or extra.get("task_status") or "")
    if not is_done_status(status):
        return False
    if extra.get("insufficient_evidence") is True:
        return False
    return extra.get("quality_gate_passed") is not False


def is_failure_row(extra: dict[str, Any], top: dict[str, Any]) -> bool:
    status = str(top.get("task_status") or extra.get("task_status") or "").lower()
    if status in {"partial", "failed", "blocked"}:
        return True
    code = str(extra.get("failure_reason_code") or "")
    return bool(code) and code not in {"success", "other", ""}


def aggregate_turn_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    partial = 0
    complex_n = 0
    complex_ok = 0
    async_n = 0
    upgrade_n = 0
    insufficiency_n = 0
    mat_counts: list[float] = []
    timings: list[float] = []
    gate_pass = 0
    gate_seen = 0
    failure_codes: Counter[str] = Counter()

    for row in rows:
        extra = dict(row.get("extra") or {})
        top = row
        status = str(row.get("task_status") or extra.get("task_status") or "")
        if status.lower() == "partial":
            partial += 1
        if is_complex_task(extra, top):
            complex_n += 1
            if is_effective_complete(extra, top):
                complex_ok += 1
        if is_async_task(extra):
            async_n += 1
        if extra.get("quality_gate.upgrade_profile") or extra.get("profile_exit_reason"):
            upgrade_n += 1
        if extra.get("insufficient_evidence") is True:
            insufficiency_n += 1

        c = extra.get("v15_retrieved_chunks_count")
        t = extra.get("v15_temporary_materials_count")
        if isinstance(c, (int, float)) or isinstance(t, (int, float)):
            mat_counts.append(float(c or 0) + float(t or 0))

        ms = extra.get("timing_total_ms") or row.get("workflow_elapsed_ms")
        if isinstance(ms, (int, float)) and ms >= 0:
            timings.append(float(ms))

        if extra.get("quality_gate_passed") is not None:
            gate_seen += 1
            if extra.get("quality_gate_passed") is True:
                gate_pass += 1

        code = str(extra.get("failure_reason_code") or "")
        if is_failure_row(extra, top) and code not in {"", "success"}:
            failure_codes[code] += 1

    timings_sorted = sorted(timings)
    p95 = None
    if timings_sorted:
        idx = max(0, int(len(timings_sorted) * 0.95) - 1)
        p95 = timings_sorted[min(idx, len(timings_sorted) - 1)]

    failures_total = sum(failure_codes.values())
    top3 = []
    for code, cnt in failure_codes.most_common(3):
        top3.append(
            {
                "code": code,
                "count": cnt,
                "share_of_failures": (cnt / failures_total) if failures_total else 0.0,
                "share_of_turns": (cnt / total) if total else 0.0,
            }
        )

    return {
        "turns_total": total,
        "eval_item_count": total,
        "complex_task_count": complex_n,
        "async_task_count": async_n,
        "partial_count": partial,
        "partial_rate": (partial / total) if total else 0.0,
        "complex_effective_complete_rate": (complex_ok / complex_n) if complex_n else None,
        "complex_upgrade_rate": (upgrade_n / complex_n) if complex_n else None,
        "insufficiency_rate": (insufficiency_n / total) if total else 0.0,
        "avg_material_count": (sum(mat_counts) / len(mat_counts)) if mat_counts else None,
        "avg_timing_total_ms": (sum(timings) / len(timings)) if timings else None,
        "p95_timing_total_ms": p95,
        "quality_gate_pass_rate": (gate_pass / gate_seen) if gate_seen else None,
        "failure_top3": top3,
    }


def compare_periods(current: dict[str, Any], previous: dict[str, Any]) -> dict[str, Any]:
    def delta(key: str):
        a, b = current.get(key), previous.get(key)
        if a is None or b is None:
            return None
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            return round(float(a) - float(b), 4)
        return None

    return {
        "current": current,
        "previous": previous,
        "delta": {
            "complex_effective_complete_rate": delta("complex_effective_complete_rate"),
            "partial_rate": delta("partial_rate"),
            "complex_upgrade_rate": delta("complex_upgrade_rate"),
            "avg_material_count": delta("avg_material_count"),
            "avg_timing_total_ms": delta("avg_timing_total_ms"),
            "quality_gate_pass_rate": delta("quality_gate_pass_rate"),
        },
    }
