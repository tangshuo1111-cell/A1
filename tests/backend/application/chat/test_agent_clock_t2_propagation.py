"""S10 — run_chat_turn passes BudgetClock to answer stage."""
from __future__ import annotations

from dataclasses import replace

import pytest
from tests.backend.application.chat.test_main_plan_cache import (
    _deps_with_counting_pan,
    _disable_fast_lanes,
)

from application.chat.run_chat_turn import run_agno_chat_turn_impl
from config import feature_flags


def test_run_chat_turn_passes_clock_to_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _disable_fast_lanes(monkeypatch)
    monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_BUDGET_CLOCK_V2", True)

    seen: dict[str, object] = {}

    def _capture_run_basic_qa(*_args, **kwargs):
        seen["clock"] = kwargs.get("clock")
        return (
            "这是一段用于集成测试的足够长的默认回答，确保 complex profile 的质量门控可以通过。"
            "包含结构与足够字符长度。"
        )

    monkeypatch.setattr(
        "application.chat.response_assembly.build_extra",
        lambda *_a, **_k: {"lane": "agno_basic", "primary_path": "agno_basic", "mode": "complex"},
    )

    deps = replace(_deps_with_counting_pan([]), run_basic_qa=_capture_run_basic_qa)

    out = run_agno_chat_turn_impl("你好", session_id="s11-pass-clock", deps=deps)
    assert out["answer"] == (
        "这是一段用于集成测试的足够长的默认回答，确保 complex profile 的质量门控可以通过。"
        "包含结构与足够字符长度。"
    )
    assert seen.get("clock") is not None
