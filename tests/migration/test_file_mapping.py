from __future__ import annotations

import csv
from pathlib import Path

CSV_PATH = Path("docs/current/migration/file_mapping.csv")


def test_file_mapping_csv_exists_and_has_required_columns() -> None:
    assert CSV_PATH.exists()
    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    assert reader.fieldnames == [
        "source_path",
        "target_path",
        "action",
        "phase",
        "status",
        "owner",
        "done_when",
        "remove_by_phase",
        "notes",
    ]
    assert rows


def test_phase3_required_coverage_exists() -> None:
    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    sources = {row["source_path"] for row in rows}
    required = {
        "backend/application/chat/run_chat_turn.py",
        "backend/agents/main_agent/*",
        "backend/agents/middle_agent/*",
        "backend/agents/answer_agent/*",
        "backend/tasks/task_runner.py",
        "backend/tasks/task_store.py",
        "backend/tasks/video_task_queue.py",
        "backend/workers/video_worker_pool.py",
        "backend/workers/entry/video_task_worker.py",
        "backend/video/*",
    }
    for item in required:
        assert item in sources, f"missing Phase 3 mapping for {item}"


def test_high_risk_actions_present() -> None:
    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    actions = {row["action"] for row in rows}
    assert "move" in actions
    assert "retain+shrink" in actions
    assert "split" in actions
