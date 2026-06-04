"""周报逐条样本附录渲染。"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.report_product_metrics import render_sample_appendix


def test_render_sample_appendix_rows() -> None:
    html = render_sample_appendix(
        [
            {
                "sample_label": "simple_01",
                "message_text": "1+1 等于多少？",
                "task_status": "succeeded",
                "failure_reason_code": "success",
                "answer_summary": "1+1 等于 2。",
                "timing_total_ms": 3100,
            }
        ]
    )
    assert "simple_01" in html
    assert "1+1 等于多少？" in html
    assert "3.10 秒" in html or "首响 3.10s" in html


def test_render_sample_appendix_async_final() -> None:
    html = render_sample_appendix(
        [
            {
                "sample_label": "async_02",
                "message_text": "抓取 NYTimes",
                "task_status": "pending",
                "failure_reason_code": "other",
                "answer_summary": "这个请求已进入网页后台抓取通道。",
                "timing_total_ms": 46,
                "async_final_answer": "军方采购英伟达芯片要点。",
                "async_poll_status": "partial",
                "async_background_ms": 13072,
            }
        ]
    )
    assert "async_02" in html
    assert "partial" in html
    assert "军方采购英伟达芯片要点" in html
    assert "后台 13.07s" in html


def test_render_sample_appendix_empty() -> None:
    assert "无逐条样本" in render_sample_appendix([])


def test_render_html_shows_sample_n_warning() -> None:
    from scripts.report_product_metrics import render_html

    html = render_html(
        {
            "period_current": "2026-06-01 – 2026-06-03",
            "period_previous": "2026-05-25 – 2026-05-31",
            "current": {
                "turns_total": 6,
                "eval_item_count": 6,
                "complex_task_count": 4,
                "async_task_count": 1,
                "failure_top3": [],
            },
            "previous": {"turns_total": 0, "eval_item_count": 0},
            "delta": {},
            "sample_appendix": [],
            "notes_template_path": "notes.md",
        }
    )
    assert "【样本 N=6】" in html
    assert "N&lt;30" in html
    assert "离线代表题" in html
