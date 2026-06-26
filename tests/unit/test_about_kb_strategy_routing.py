"""About-KB strategy questions stay general-lane (C2 / KI-METRICS-004)."""

from __future__ import annotations

from application.ingress.lane_selector import select_lane
from application.ingress.request_classifier import classify_request


def test_about_kb_strategy_stays_general_lane():
    msg = (
        "请综合评估在知识库问答里『全量自动沉淀所有资料』与"
        "『先解析、用户确认后再收录』两种产品策略，并给出推荐。"
    )
    signals = classify_request(
        message=msg,
        use_knowledge=False,
        v13_file_content=None,
        v13_text_content=None,
    )
    assert signals.has_kb_intent is False
    assert select_lane(signals)[0] == "general"


def test_kb_query_still_has_kb_intent():
    msg = "根据知识库说明一下这个项目的资料处理主链。"
    signals = classify_request(
        message=msg,
        use_knowledge=False,
        v13_file_content=None,
        v13_text_content=None,
    )
    assert signals.has_kb_intent is True
