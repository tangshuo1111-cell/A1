"""第三轮：answer_flow 拼装与空结果语义。"""
from __future__ import annotations

import sys

from tests._support.bootstrap import find_repo_root

REPO_ROOT = find_repo_root(__file__)
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agents.answer_agent.answer_flow import answer  # noqa: E402
from agents.answer_agent.answer_flow_compose import _evidence_to_user_bullets  # noqa: E402
from schemas import EvidencePack, MainDecision  # noqa: E402


def _dec_kb(**kw: object) -> MainDecision:
    base = dict(
        task_id="af-1",
        need_rag=True,
        router_source="rules",
        answer_channel="kb",
    )
    base.update(kw)
    return MainDecision(**base)  # type: ignore[arg-type]


def test_long_evidence_truncated_in_bullets() -> None:
    src = ["起" + ("这是一段需要被截断的占位文字。" * 20)]
    lines = _evidence_to_user_bullets(src, "general")
    assert lines
    line0 = lines[0]
    assert "…" in line0 or len(line0) <= 330


def test_empty_evidence_kb_has_insufficient_notice() -> None:
    ev = EvidencePack(
        task_id="af-empty",
        evidence_list=[],
        key_evidence_list=[],
        completeness_ok=False,
        missing_info="",
        evidence_state="not_found",
    )
    dec = _dec_kb(primary_goal="缺省目标")
    ar = answer("本地没有命中的话题 xyz", ev, decision=dec)
    assert ar.has_insufficient_info_notice is True
    assert "知识库" in ar.final_answer or "资料" in ar.final_answer


def test_direct_channel_thanks_no_kb_leak() -> None:
    """正常生成：direct 回答忌提「检索/缺口」类内部语气（白名单式断言）。"""
    ev = EvidencePack(
        task_id="af-direct",
        evidence_list=[],
        key_evidence_list=[],
        completeness_ok=True,
        missing_info="",
        evidence_state="",
    )
    dec = MainDecision(
        task_id="af-direct",
        need_rag=False,
        need_external_info=False,
        need_tool_local=False,
        answer_channel="direct",
        router_source="rules",
    )
    ar = answer("谢谢", ev, decision=dec)
    lower = ar.final_answer.lower()
    assert "not_found" not in lower
    assert "gap_notes" not in lower
    assert len(ar.final_answer.strip()) > 2
