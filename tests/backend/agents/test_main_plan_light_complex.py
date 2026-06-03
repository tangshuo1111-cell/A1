from __future__ import annotations

from types import SimpleNamespace

from agents.main_agent.main_invoke_flow import _build_plan_params, _PlanParams, _V13Result


def _v13_none() -> _V13Result:
    return _V13Result(
        prepare_intent=None,
        commit_intent=False,
        llm_signal="skip",
        llm_error="",
    )


def test_decision_support_prefers_light_complex_without_explicit_evidence_request() -> None:
    decision = SimpleNamespace(need_rag=True)
    xiezuo_pan = SimpleNamespace(allow_kb=True, allow_web=False)

    plan: _PlanParams = _build_plan_params(
        "我在大厂做了 5 年，现在拿到一个降薪 30% 的创业公司 offer。请从职业成长、风险、现金流、安全边际三个角度帮我做决策。",
        decision,
        xiezuo_pan,
        False,
        _v13_none(),
        None,
        False,
    )

    assert plan.needs_retrieval is False
    assert plan.answer_mode == "direct"
    assert "retrieve_knowledge" not in plan.tools


def test_explicit_kb_request_keeps_knowledge_grounded() -> None:
    decision = SimpleNamespace(need_rag=True)
    xiezuo_pan = SimpleNamespace(allow_kb=True, allow_web=False)

    plan: _PlanParams = _build_plan_params(
        "请结合知识库中的资料，从职业成长、风险、现金流、安全边际三个角度帮我做决策。",
        decision,
        xiezuo_pan,
        False,
        _v13_none(),
        None,
        False,
    )

    assert plan.needs_retrieval is True
    assert plan.answer_mode == "knowledge_grounded"
    assert "retrieve_knowledge" in plan.tools
