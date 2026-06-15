"""Complex path background task exit lift."""

from __future__ import annotations

from dataclasses import dataclass, field

from application.chat.pending_kind import PendingKind
from application.chat.turn_facts import TurnFacts, lift_background_task_exit


@dataclass
class _Envelope:
    task_id: str = ""


@dataclass
class _Bundle:
    evidence_envelopes: list[_Envelope] = field(default_factory=list)


def test_lift_sets_async_pending_and_processing_kind():
    facts = TurnFacts(effective_mode="complex", executor_profile="complex")
    bundle = _Bundle(evidence_envelopes=[_Envelope(task_id="bg-42")])
    lifted, extra, task_id = lift_background_task_exit(facts=facts, extra={}, bundle=bundle)
    assert task_id == "bg-42"
    assert lifted.async_pending is True
    assert lifted.pending_kind == PendingKind.PROCESSING_PENDING
    assert lifted.legacy_task_status == "pending"
    assert "next_action" in extra
