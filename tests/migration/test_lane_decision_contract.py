from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from application.chat.budget_clock import BudgetClock
from application.ingress import LaneDecision, route_chat_request

SAMPLES = sorted(Path("docs/current/baselines/samples").glob("*.yaml"))


@pytest.mark.parametrize("path", SAMPLES, ids=lambda p: p.stem)
def test_sample_after_migration_yields_valid_lane_decision(path: Path) -> None:
    sample = yaml.safe_load(path.read_text(encoding="utf-8"))
    payload = sample["input"]
    attachments = list(payload.get("attachments") or [])
    decision = route_chat_request(
        message=payload["message"],
        session_id=payload.get("session_id"),
        request_id=f"lane-{path.stem}",
        use_knowledge=bool(payload.get("use_knowledge", False)),
        v13_file_content=b"sample-bytes" if attachments else None,
        v13_text_content=None,
        attachments=attachments,
        clock=BudgetClock.start(),
    )
    LaneDecision.model_validate(decision.model_dump())
    acceptance = sample["acceptance_after_migration"]
    assert decision.lane == acceptance["lane"]
    assert decision.mode in acceptance["mode_either_of"]
