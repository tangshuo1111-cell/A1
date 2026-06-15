from __future__ import annotations

from application.chat.complexity_policy import (
    STRONG_COMPLEX_REASON_CODES,
    evaluate_complex_candidate,
)
from application.ingress.mode_selector import select_mode
from application.ingress.request_classifier import classify_request

_INTERVIEW_MESSAGE = (
    "请帮我把这个项目讲成面试官能听懂的话：它为什么不是普通 RAG，"
    "而是一个带 route、capability、multi-turn state、agent collaboration 评测体系的项目？"
)


def test_interview_explanation_is_complex_candidate_with_strong_codes() -> None:
    signal = evaluate_complex_candidate(_INTERVIEW_MESSAGE)
    assert signal.complex_candidate is True
    assert "structured_explanation" in signal.reason_codes
    assert bool(set(signal.reason_codes) & STRONG_COMPLEX_REASON_CODES)


def test_mode_selector_routes_interview_explanation_to_complex() -> None:
    signal = evaluate_complex_candidate(_INTERVIEW_MESSAGE)
    signals = classify_request(
        message=_INTERVIEW_MESSAGE,
        use_knowledge=True,
        v13_file_content=None,
        v13_text_content=None,
    )
    mode, _confidence = select_mode(
        lane="general",
        signals=signals,
        message=_INTERVIEW_MESSAGE,
        complex_candidate=signal.complex_candidate,
        complex_reason_codes=signal.reason_codes,
    )
    assert mode == "complex"
