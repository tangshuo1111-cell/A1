"""turn_product_metrics PG 读写（仅存储，不做业务判断）。"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from psycopg.rows import dict_row

from storage.pg_pool import get_pool

logger = logging.getLogger("light_maqa")


def insert_turn_product_metrics(
    *,
    task_id: str,
    session_id: str | None,
    request_id: str | None,
    task_status: str,
    mode: str | None,
    executor_profile: str | None,
    is_complex_task: bool,
    quality_gate_passed: bool | None,
    insufficient_evidence: bool,
    timing_total_ms: int | None,
    answer_char_count: int | None,
    retrieved_chunks_count: int,
    temporary_materials_count: int,
    failure_reason_code: str | None,
    sample_label: str | None = None,
    message_text: str | None = None,
    answer_summary: str | None = None,
) -> None:
    try:
        pool = get_pool()
        with pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO turn_product_metrics (
                    task_id, session_id, request_id, created_at,
                    task_status, mode, executor_profile,
                    is_complex_task, quality_gate_passed, insufficient_evidence,
                    timing_total_ms, answer_char_count,
                    retrieved_chunks_count, temporary_materials_count,
                    failure_reason_code, sample_label, message_text, answer_summary
                ) VALUES (
                    %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s,
                    %s, %s,
                    %s, %s, %s, %s
                );
                """,
                (
                    task_id,
                    session_id,
                    request_id,
                    datetime.now(UTC).isoformat(),
                    task_status,
                    mode,
                    executor_profile,
                    bool(is_complex_task),
                    quality_gate_passed,
                    bool(insufficient_evidence),
                    timing_total_ms,
                    answer_char_count,
                    int(retrieved_chunks_count),
                    int(temporary_materials_count),
                    failure_reason_code,
                    sample_label,
                    message_text,
                    answer_summary,
                ),
            )
            conn.commit()
    except Exception as exc:  # noqa: BLE001 — soft fail，不挡用户回答
        logger.warning("turn_product_metrics insert failed task_id=%s err=%s", task_id, exc)


def update_turn_product_metrics_async_completion(
    *,
    task_id: str,
    async_final_answer: str | None = None,
    async_poll_status: str | None = None,
    async_background_ms: int | None = None,
    answer_summary: str | None = None,
) -> bool:
    """沙箱 / 运维：async 任务 poll 完成后回写终答与后台耗时（按 task_id 匹配首响行）。"""
    tid = (task_id or "").strip()
    if not tid:
        return False
    final = (async_final_answer or "").strip() or None
    summary = (answer_summary or "").strip() or None
    if final and not summary:
        summary = final[:320]
    poll_st = (async_poll_status or "").strip() or None
    bg_ms = int(async_background_ms) if async_background_ms is not None else None
    if not any((final, poll_st, bg_ms is not None, summary)):
        return False
    try:
        pool = get_pool()
        with pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE turn_product_metrics
                SET async_final_answer = COALESCE(%s, async_final_answer),
                    async_poll_status = COALESCE(%s, async_poll_status),
                    async_background_ms = COALESCE(%s, async_background_ms),
                    answer_summary = COALESCE(%s, answer_summary)
                WHERE task_id = %s;
                """,
                (final, poll_st, bg_ms, summary, tid),
            )
            conn.commit()
            return cur.rowcount > 0
    except Exception as exc:  # noqa: BLE001
        logger.warning("turn_product_metrics async update failed task_id=%s err=%s", tid, exc)
        return False


def fetch_metrics_between(iso_start: str, iso_end: str) -> list[dict[str, Any]]:
    pool = get_pool()
    with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT *
            FROM turn_product_metrics
            WHERE created_at >= %s AND created_at < %s
            ORDER BY created_at ASC;
            """,
            (iso_start, iso_end),
        )
        return [dict(r) for r in cur.fetchall()]
