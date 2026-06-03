from __future__ import annotations

import json
from pathlib import Path


def test_questions_v1_schema() -> None:
    path = Path(__file__).resolve().parents[2] / "benchmarks" / "agent_eval" / "questions_v1.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["benchmark_id"] == "agent-eval-v1"
    assert isinstance(data["questions"], list)
    assert len(data["questions"]) == 12
    ids = [item["id"] for item in data["questions"]]
    assert len(ids) == len(set(ids))
    for item in data["questions"]:
        assert item["prompt"]
        assert item["category"]


def test_baseline_schema() -> None:
    path = Path(__file__).resolve().parents[2] / "benchmarks" / "agent_eval" / "baseline_2026-05-26.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["benchmark_id"] == "agent-eval-2026-05-26-a"
    assert "summary" in data
    assert "item_scores" in data
    assert len(data["item_scores"]) == 12
