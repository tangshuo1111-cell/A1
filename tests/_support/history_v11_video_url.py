"""Shared helpers extracted from the large V11 video URL historical suite."""

from __future__ import annotations


def bili_url() -> str:
    return "https://www.bilibili.com/video/BV1xx411c7mD"


def yt_url() -> str:
    return "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def fake_llm_classifier(intent: str = "zhijie_yitu"):
    from llm.router import LlmIntentResult

    calls: list[str] = []

    def _fake(message: str) -> LlmIntentResult:
        calls.append(message)
        return LlmIntentResult.ok(intent, "fake")

    _fake.calls = calls  # type: ignore[attr-defined]
    return _fake


def unavailable_classifier():
    from llm.router import LlmIntentResult

    calls: list[str] = []

    def _fake(message: str) -> LlmIntentResult:
        calls.append(message)
        return LlmIntentResult.unavailable("llm_unavailable")

    _fake.calls = calls  # type: ignore[attr-defined]
    return _fake
