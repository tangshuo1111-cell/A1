"""S0 scaffold acceptance — compat tooling, flags, contract stubs."""
from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
COMPAT_CSV = PROJECT_ROOT / "docs" / "current" / "migration" / "compat_retirement.csv"
CHAT_TESTS = PROJECT_ROOT / "tests" / "backend" / "application" / "chat"
CAP_TESTS = PROJECT_ROOT / "tests" / "backend" / "services" / "capabilities"


def _run_script(script: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / script), *args],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


class TestS0Scaffold:
    def test_compat_retirement_csv_exists(self):
        assert COMPAT_CSV.exists()

    def test_compat_retirement_csv_columns(self):
        with COMPAT_CSV.open(newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        assert rows, "compat_retirement.csv should have at least one row"
        required = {
            "item_type",
            "item_id",
            "introduced_release",
            "delete_by_release",
            "status",
            "owner",
            "delete_pr",
        }
        assert required.issubset(set(rows[0].keys()))

    def test_check_compat_field_writes_ok_with_pending_rules(self):
        proc = _run_script("check_compat_field_writes.py")
        assert proc.returncode == 0, proc.stderr or proc.stdout

    def test_check_compat_retirement_ok_before_s11(self):
        proc = _run_script("check_compat_retirement.py", "--current-release", "S0")
        assert proc.returncode == 0, proc.stderr or proc.stdout

    def test_test_directories_exist(self):
        assert CHAT_TESTS.is_dir()
        assert CAP_TESTS.is_dir()

    def test_contract_stubs_importable(self):
        from application.chat.pending_kind import PendingKind
        from application.ingress.main_plan_hints import MainPlanHints
        from services.capabilities.contracts import (
            CapabilityAdvice,
            CapabilityFact,
            EvidenceEnvelope,
        )

        assert PendingKind.NONE.value == "none"
        assert MainPlanHints().router_reason == ""
        fact = CapabilityFact(lane="video", probe_elapsed_ms=0)
        advice = CapabilityAdvice(suggested_mode="sync_ok", reason="stub")
        env = EvidenceEnvelope(source="test", lane="video", outcome="ok", elapsed_ms=1)
        assert fact.lane == "video"
        assert advice.suggested_mode == "sync_ok"
        assert env.outcome == "ok"

    def test_default_feature_flags_valid(self):
        from config.feature_flags import FEATURE_FLAGS, validate_flag_combination

        assert validate_flag_combination(FEATURE_FLAGS) == []
