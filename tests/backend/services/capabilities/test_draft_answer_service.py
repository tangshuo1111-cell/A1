"""S9 — answer_draft service + light critic."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from config import feature_flags
from services.capabilities import answer_draft


@pytest.fixture
def enable_draft_answer(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_DRAFT_ANSWER_V2", True)


def test_build_draft_answer_uses_fast_llm_when_flag_on(enable_draft_answer) -> None:
    material = "视频讲述了异步任务与 final_answer 闭环。" * 20
    with patch.object(answer_draft, "_call_fast_llm", return_value="这是后台草稿总结。"):
        result = answer_draft.build_draft_answer(
            lane="video",
            user_query="请总结视频",
            material=material,
            title="demo.mp4",
        )
    assert result.draft is True
    assert result.answer == "这是后台草稿总结。"
    assert result.critic_check.get("unsupported_claims") == []
    assert result.limitations


def test_build_draft_answer_video_prompt_requests_structured_points(enable_draft_answer) -> None:
    material = "视频讲了选择不可怕，要先行动，再在过程中调整方向。" * 20
    captured: dict[str, str] = {}

    def _fake_call(prompt: str) -> str:
        captured["prompt"] = prompt
        return "1. 要点一。\n\n2. 要点二。\n\n3. 要点三。"

    with patch.object(answer_draft, "_call_fast_llm", side_effect=_fake_call):
        result = answer_draft.build_draft_answer(
            lane="video",
            user_query="请总结视频",
            material=material,
            title="demo.mp4",
        )
    assert "3-5 个要点" in captured["prompt"]
    assert "结构化总结" in captured["prompt"]
    assert result.answer.startswith("1. 要点一。")


def test_build_draft_answer_falls_back_without_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_DRAFT_ANSWER_V2", False)
    material = "fallback material text"
    with patch.object(
        answer_draft,
        "_call_fast_llm",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("llm must not run")),
    ):
        result = answer_draft.build_draft_answer(
            lane="web",
            user_query="总结网页",
            material=material,
        )
    assert result.answer == material
    assert result.critic_check.get("unsupported_claims") == []


def test_build_draft_answer_video_fallback_is_structured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_DRAFT_ANSWER_V2", False)
    material = "第一句。第二句。第三句。第四句。"
    result = answer_draft.build_draft_answer(
        lane="video",
        user_query="总结视频",
        material=material,
        title="demo.mp4",
    )
    assert "1." in result.answer
    assert "2." in result.answer


def test_light_critic_rejects_empty_answer() -> None:
    critic = answer_draft.run_light_critic(answer="", material="some material")
    assert critic["unsupported_claims"]
    assert critic["revision_required"] is True


def test_final_answer_fields_for_task_includes_critic_metadata() -> None:
    fields = answer_draft.final_answer_fields_for_task(
        lane="document",
        user_query="report.pdf",
        material="文档正文内容。",
        title="report.pdf",
    )
    assert fields["final_answer"]
    assert fields["draft"] is True
    assert fields["draft_critic_check"]["unsupported_claims"] == []
