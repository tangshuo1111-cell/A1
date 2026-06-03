from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from application.chat.budget_clock import BudgetClock
from application.ingress import route_chat_request

SAMPLES = sorted(Path("docs/current/baselines/samples").glob("*.yaml"))
LANES = {"video", "document", "web", "kb", "general"}
MODES = {"fast", "complex", "async"}
ROUTER_SOURCES = {"rule", "light_classifier", "main_agent"}


@pytest.mark.parametrize("path", SAMPLES, ids=lambda p: p.stem)
def test_ingress_router_trace_contains_required_prod_fields(path: Path) -> None:
    sample = yaml.safe_load(path.read_text(encoding="utf-8"))
    payload = sample["input"]
    attachments = list(payload.get("attachments") or [])
    decision = route_chat_request(
        message=payload["message"],
        session_id=payload.get("session_id"),
        request_id=f"trace-{path.stem}",
        use_knowledge=bool(payload.get("use_knowledge", False)),
        v13_file_content=b"sample-bytes" if attachments else None,
        v13_text_content=None,
        attachments=attachments,
        clock=BudgetClock.start(),
    ).model_dump()
    assert decision["request_id"]
    assert decision["lane"] in LANES
    assert decision["mode"] in MODES
    assert decision["router_source"] in ROUTER_SOURCES
    assert 0.0 <= float(decision["router_confidence"]) <= 1.0
