from __future__ import annotations

import csv
from pathlib import Path

import pytest
from tests.baselines._support.perf_probe import load_samples, run_sample_perf, sample_sla_ms

PERF_CSV = Path("docs/current/baselines/perf_baseline.csv")
META_YAML = Path("docs/current/baselines/perf_baseline_meta.yaml")


def _load_perf_rows() -> dict[str, dict[str, str]]:
    with PERF_CSV.open("r", encoding="utf-8-sig", newline="") as handle:
        return {str(row["sample_id"]).strip(): row for row in csv.DictReader(handle)}


@pytest.mark.parametrize("sample", load_samples(), ids=lambda s: s["sample_id"])
def test_new_path_first_response_within_sample_sla(sample: dict) -> None:
    sla = sample_sla_ms(sample)
    assert sla is not None, f"missing first_response_ms_le for {sample['sample_id']}"
    row = run_sample_perf(sample)
    assert row.success is True
    assert row.first_response_ms <= sla, (
        f"{sample['sample_id']} first_response_ms={row.first_response_ms} > sla={sla}"
    )


@pytest.mark.parametrize("sample", load_samples(), ids=lambda s: s["sample_id"])
def test_perf_baseline_csv_matches_live_probe_within_tolerance(sample: dict) -> None:
    stored = _load_perf_rows()[sample["sample_id"]]
    live = run_sample_perf(sample)
    stored_first = int(stored["first_response_ms"])
    # Allow 3x drift for CI machine variance; SLA test is the hard gate.
    assert live.first_response_ms <= max(stored_first * 3, stored_first + 500)
    assert str(stored["success"]).lower() == "true"


def test_perf_baseline_meta_exists_for_p10_recapture() -> None:
    assert META_YAML.exists()
    text = META_YAML.read_text(encoding="utf-8")
    assert "architecture_path:" in text
    assert "ingress_v2_fast_complex_lanes" in text
