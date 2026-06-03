"""§5.7 — collaboration trace writer."""
from __future__ import annotations

from application.chat.trace_writer import (
    append_arbitrator_trace,
    apply_arbitrator_extra,
    trace_record,
)


def test_trace_record_schema():
    rec = trace_record(
        stage="capability",
        name="video_probe",
        elapsed_ms=120,
        outcome="partial",
        reason="probe_budget_exceeded",
    )
    assert rec == {
        "stage": "capability",
        "name": "video_probe",
        "elapsed_ms": 120,
        "outcome": "partial",
        "reason": "probe_budget_exceeded",
    }


def test_apply_arbitrator_extra_merges_trace():
    extra = apply_arbitrator_extra(
        {"lane": "video"},
        ingress_mode="fast",
        decided_mode="async",
        decided_reason="capability_demote_to_async",
        collaboration_trace=append_arbitrator_trace(
            [],
            name="mode_decision",
            decided_mode="async",
            reason="capability_demote_to_async",
            elapsed_ms=3,
        ),
    )
    assert extra["mode"] == "async"
    assert extra["arbitrator.decided_mode"] == "async"
    assert extra["arbitrator.decided_reason"] == "capability_demote_to_async"
    assert extra["collaboration_trace"][0]["stage"] == "arbitrator"
