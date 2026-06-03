from __future__ import annotations

import json
import tempfile
from pathlib import Path

from scripts.benchmarks.render_agent_eval_report import render_report
from scripts.benchmarks.run_agent_eval import build_parser, load_questions
from scripts.benchmarks.score_agent_eval import summarize


def test_load_questions_reads_v1() -> None:
    path = Path(__file__).resolve().parents[2] / "benchmarks" / "agent_eval" / "questions_v1.json"
    data = load_questions(path)
    assert data["benchmark_id"] == "agent-eval-v1"
    assert len(data["questions"]) == 12


def test_build_parser_defaults_to_local_runner() -> None:
    parser = build_parser()
    args = parser.parse_args([])
    assert args.runner == "local"


def test_summarize_raw_result_shape() -> None:
    sample = [
        {"id": "Q1", "http_status": 200, "extra": {"mode": "complex"}, "answer": "ok"},
        {"id": "Q2", "http_status": 500, "raw_text": "Internal Server Error"},
        {"id": "Q3", "http_status": 200, "extra": {"mode": "fast"}, "answer": "ok"},
    ]
    out = summarize(sample)
    assert out["total"] == 3
    assert out["http_500"] == 1
    assert out["fast"] == 1
    assert out["complex"] == 1


def test_summary_file_roundtrip() -> None:
    payload = {"source_results": "x", "summary": {"total": 1}, "items": []}
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "sample.summary.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        loaded = json.loads(path.read_text(encoding="utf-8"))
        assert loaded["summary"]["total"] == 1


def test_render_report_outputs_markdown() -> None:
    scored = {
        "summary": {
            "average_score_all": 5.7,
            "average_score_without_major_failures": 6.7,
            "major_failure_ids": ["Q2"],
            "best_agent_cases": ["Q1"],
            "conclusion": "ok",
        },
        "items": [
            {
                "id": "Q1",
                "score": 8.7,
                "routing": {
                    "primary_path": "agno_basic",
                    "mode": "complex",
                    "http_status": 200,
                    "elapsed_s": 19.3,
                },
                "dimension_scores": {
                    "structure": 9.0,
                    "reasoning_depth": 8.0,
                    "multi_view": 8.0,
                    "evidence_sense": 7.0,
                    "prudence": 9.0,
                    "actionability": 10.0,
                },
                "judgment": "good",
            }
        ],
    }
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "report.md"
        text = render_report(benchmark_id="demo-benchmark", scored=scored, output_path=out)
        assert out.exists()
        assert "# Agent 评测基准报告：demo-benchmark" in text
        assert "| Q1 | `agno_basic` | `complex` | 200 | 19.3 | 8.7 | Agent 主链样本 |" in text
