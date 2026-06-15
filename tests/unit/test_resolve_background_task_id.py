"""Background task id resolution for async polling contract."""

from __future__ import annotations

from dataclasses import dataclass, field

from application.chat.chat_contracts import resolve_background_task_id


@dataclass
class _Envelope:
    task_id: str = ""


@dataclass
class _Bundle:
    evidence_envelopes: list[_Envelope] = field(default_factory=list)
    tool_calls: list[dict] = field(default_factory=list)


def test_resolve_from_extra_background_task_id():
    assert resolve_background_task_id(extra={"background_task_id": "job-123"}) == "job-123"


def test_resolve_skips_fast_placeholder():
    assert resolve_background_task_id(extra={"task_id": "fast-abc"}) == ""


def test_resolve_from_bundle_evidence_envelope():
    bundle = _Bundle(evidence_envelopes=[_Envelope(task_id="env-task-1")])
    assert resolve_background_task_id(extra={}, bundle=bundle) == "env-task-1"


def test_resolve_from_tool_call_metadata():
    bundle = _Bundle(
        tool_calls=[{"metadata": {"background_task_id": "asr-mid-9"}}],
    )
    assert resolve_background_task_id(extra={}, bundle=bundle) == "asr-mid-9"


def test_resolve_from_nested_tool_result_metadata():
    bundle = _Bundle(
        tool_calls=[{
            "tool": "asr_transcribe",
            "result": {
                "status": "queued",
                "metadata": {"background_task_id": "asr-queued-7"},
            },
        }],
    )
    assert resolve_background_task_id(extra={}, bundle=bundle) == "asr-queued-7"
