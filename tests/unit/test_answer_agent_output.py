"""answer_agent：用户正文不得含内部标签与写作提示。"""

from agents import answer_agent
from schemas import EvidencePack, MainDecision


def _pack_with_evidence(texts: list[str]) -> EvidencePack:
    return EvidencePack(
        task_id="t1",
        evidence_list=texts,
        key_evidence_list=[],
        completeness_ok=True,
        missing_info="",
        evidence_state="ok",
    )


def test_answer_no_style_hint_leak():
    ev = _pack_with_evidence(["项目代号是 LightMultiAgentQA，用于演示多 Agent 流程。"])
    dec = MainDecision(
        task_id="t1",
        need_rag=True,
        answer_channel="kb",
        answer_style="general",
        answer_style_hint="这是内部提示：请用学术语气",
        primary_goal="项目代号",
        router_source="rules",
    )
    ar = answer_agent.answer("项目代号是什么？", ev, decision=dec)
    assert "写作提示" not in ar.final_answer
    assert "answer_style_hint" not in ar.final_answer.lower()
    assert "[doc_path]" not in ar.final_answer


def test_answer_no_doc_meta_when_evidence_sanitized():
    ev = _pack_with_evidence(["示例文档在 knowledge_samples 目录，描述三 Agent 分工。"])
    dec = MainDecision(
        task_id="t1",
        need_rag=True,
        answer_channel="kb",
        primary_goal="文档位置",
        router_source="rules",
    )
    out = answer_agent.answer("示例文档在哪？", ev, decision=dec)
    assert "[doc_file]" not in out.final_answer
    assert "[demo_keywords]" not in out.final_answer


def test_insufficient_kb_no_banned_tokens():
    ev = EvidencePack(
        task_id="t1",
        evidence_list=[],
        completeness_ok=False,
        missing_info="",
        evidence_state="not_found",
    )
    dec = MainDecision(
        task_id="t1",
        need_rag=True,
        answer_channel="kb",
        primary_goal="不存在的主题",
        answer_style_hint="内部",
        router_source="rules",
    )
    out = answer_agent.answer("xyzabc 不存在的内容？", ev, decision=dec)
    assert "写作提示" not in out.final_answer
    assert "gap_notes" not in out.final_answer
