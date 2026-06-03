from __future__ import annotations

import csv
import json
from pathlib import Path

BASE_DIR = Path("docs/current/baselines")
SAMPLES_DIR = BASE_DIR / "samples"
TRACE_DIR = BASE_DIR / "trace_baseline"
TRACE_NEW_DIR = BASE_DIR / "trace_baseline_new"


def _extract_sample_id(path: Path) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("sample_id:"):
            return line.split(":", 1)[1].strip()
    raise AssertionError(f"sample_id missing in {path}")


def test_phase0_baseline_files_exist() -> None:
    assert (BASE_DIR / "request_catalog.yaml").exists()
    assert (BASE_DIR / "perf_baseline.csv").exists()
    assert SAMPLES_DIR.exists()
    assert TRACE_DIR.exists()
    assert TRACE_NEW_DIR.exists()


def test_phase0_has_at_least_seven_request_samples() -> None:
    sample_files = sorted(SAMPLES_DIR.glob("*.yaml"))
    assert len(sample_files) >= 7


def test_every_sample_has_matching_trace_baseline() -> None:
    sample_files = sorted(SAMPLES_DIR.glob("*.yaml"))
    assert sample_files
    for sample in sample_files:
        sample_id = _extract_sample_id(sample)
        trace_file = TRACE_DIR / f"{sample_id}.trace.json"
        assert trace_file.exists(), f"missing trace baseline for {sample_id}"
        payload = json.loads(trace_file.read_text(encoding="utf-8"))
        assert payload["sample_id"] == sample_id


def test_perf_baseline_covers_all_samples() -> None:
    sample_ids = {_extract_sample_id(path) for path in SAMPLES_DIR.glob("*.yaml")}
    with (BASE_DIR / "perf_baseline.csv").open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    perf_ids = {str(row["sample_id"]).strip() for row in rows}
    assert sample_ids
    assert sample_ids <= perf_ids

