"""Round 21 — observability dashboard/alert closed loop."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _run(script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / script)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_observability_artifacts_exist() -> None:
    assert (PROJECT_ROOT / "docs" / "current" / "observability" / "alert_rules.yaml").is_file()
    assert (PROJECT_ROOT / "docs" / "current" / "observability" / "dashboard_panels.json").is_file()
    assert (
        PROJECT_ROOT / "docs" / "current" / "observability" / "prometheus_scrape.example.yml"
    ).is_file()


def test_dashboard_panels_reference_prometheus_path() -> None:
    data = json.loads(
        (PROJECT_ROOT / "docs" / "current" / "observability" / "dashboard_panels.json").read_text(
            encoding="utf-8"
        )
    )
    assert data["scrape_path"] == "/internal/metrics/prometheus"
    assert len(data["panels"]) >= 3


def test_check_observability_health_passes_on_clean_metrics() -> None:
    from observability import reset_metrics_for_tests

    reset_metrics_for_tests()
    proc = _run("check_observability_health.py")
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_record_metrics_trend_appends_jsonl(tmp_path: Path) -> None:
    out = tmp_path / "trend.jsonl"
    proc = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "record_metrics_trend.py"),
            "--out",
            str(out),
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    lines = out.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert "ts" in row
    assert isinstance(row.get("counters"), dict)


def test_metrics_prometheus_text_format() -> None:
    from observability import (
        metrics_prometheus_text,
        metrics_record_chat_sync,
        reset_metrics_for_tests,
    )

    reset_metrics_for_tests()
    metrics_record_chat_sync(True)
    text = metrics_prometheus_text()
    assert "light_maqa_counter_chat_sync_total 1" in text
