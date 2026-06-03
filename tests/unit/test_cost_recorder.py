"""core.cost_recorder：请求级聚合与 flush。"""

from __future__ import annotations

import sys

import pytest
from tests._support.bootstrap import find_repo_root

REPO_ROOT = find_repo_root(__file__)
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core import cost_recorder  # noqa: E402
from core.request_context import (  # noqa: E402
    get_request_id,
    new_request_id,
    set_request_id,
)


@pytest.fixture(autouse=True)
def _reset_request_id() -> None:
    set_request_id("")
    yield
    set_request_id("")
    with cost_recorder._lock:
        cost_recorder._records.clear()


def test_record_llm_ignored_without_request_id() -> None:
    set_request_id("")
    cost_recorder.record_llm_call("m", 10, 20, 0.01)
    assert cost_recorder.get_accumulated_cost() == 0.0


def test_accumulates_per_request_id() -> None:
    rid = new_request_id()
    cost_recorder.record_llm_call("gpt-test", 1, 1, 0.02)
    cost_recorder.record_llm_call("gpt-test", 2, 0, 0.01)
    assert abs(cost_recorder.get_accumulated_cost(rid) - 0.03) < 1e-9
    assert get_request_id() == rid


def test_explicit_request_id_argument() -> None:
    rid = "manual-rid-1"
    set_request_id(rid)
    cost_recorder.record_llm_call("x", 0, 0, 0.5)
    assert abs(cost_recorder.get_accumulated_cost("other")) < 1e-9
    assert abs(cost_recorder.get_accumulated_cost(rid) - 0.5) < 1e-9


def test_flush_returns_summary_and_clears() -> None:
    rid = new_request_id()
    cost_recorder.record_llm_call("z", 3, 4, 0.0)
    cost_recorder.record_tool_call("t", 1.0, True)
    summary = cost_recorder.flush_request_cost(rid)
    assert summary is not None
    assert summary["request_id"] == rid
    assert summary["llm_calls"] == 1
    assert summary["tool_calls"] == 1
    with cost_recorder._lock:
        assert rid not in cost_recorder._records


def test_get_accumulated_zero_after_flush() -> None:
    rid = new_request_id()
    cost_recorder.record_llm_call("z", 1, 1, 0.04)
    cost_recorder.flush_request_cost(rid)
    assert cost_recorder.get_accumulated_cost(rid) == 0.0
