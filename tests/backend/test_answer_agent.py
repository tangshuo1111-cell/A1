from agents import answer_agent
from application.chat.budget_clock import BudgetClock
from schemas import EvidencePack, MainDecision


def _decision(style: str = "explain", *, channel: str = "kb") -> MainDecision:
    return MainDecision(
        task_id="t1",
        need_rag=True,
        need_context=False,
        need_external_info=False,
        need_tool_local=False,
        task_status="routed",
        primary_goal="测试目标",
        answer_style=style,
        answer_style_hint="测试提示",
        router_source="rules",
        answer_channel=channel,
    )


def test_answer_has_three_sections():
    ev = EvidencePack(
        task_id="t1",
        evidence_list=["证据A 内容足够长用于测试"],
        key_evidence_list=[],
        completeness_ok=True,
        evidence_state="ok",
    )
    r = answer_agent.answer("什么是 X", ev, decision=_decision("explain"))
    assert "补充：" in r.final_answer
    assert "·" in r.final_answer or "证据A" in r.final_answer
    assert "写作提示" not in r.final_answer
    assert "测试提示" not in r.final_answer
    assert r.answer_type == "concept_explain"


def test_answer_insufficient_type():
    ev = EvidencePack(
        task_id="t1",
        evidence_list=[],
        completeness_ok=False,
        evidence_state="not_found",
    )
    r = answer_agent.answer("未知问题", ev, decision=_decision())
    assert r.has_insufficient_info_notice is True
    assert r.answer_type == "insufficient"
    assert "知识库" in r.final_answer and "没有找到" in r.final_answer
    assert "zero_rag_hit" not in r.final_answer
    assert "not_found" not in r.final_answer


def test_answer_direct_skips_internal_labels():
    ev = EvidencePack(
        task_id="t1",
        evidence_list=[],
        completeness_ok=False,
        evidence_state="not_found",
        gap_categories=["zero_rag_hit"],
    )
    r = answer_agent.answer("如何打开易拉罐", ev, decision=_decision("general", channel="direct"))
    assert r.task_status == "succeeded"
    assert "not_found" not in r.final_answer
    assert "zero_rag_hit" not in r.final_answer
    assert "易拉罐" in r.final_answer


# ---------------------------------------------------------------------------
# V6 第 5 轮：AnswerAgent 已收成「唯一 Final Answer 主体 + 内部 LLM 执行器」。
# 这一组测试不走 service，直接：MainAgent → MiddleAgent → AnswerAgent，
# 并用 fake 执行器替换内部 _AgnoLlmZhixingQi，验证 answer 自身产出 HuidaPan 与 hint。
# ---------------------------------------------------------------------------
class _FakeZhixing:
    """注入用 fake LLM 执行器（answer 的内部执行器接口契约：shengcheng）。"""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def shengcheng(
        self,
        user_message,
        *,
        context_block,
        knowledge_block,
        web_search_block,
        executor_hint,
    ) -> str:
        self.calls.append(
            {
                "user_message": user_message,
                "context_block": context_block,
                "knowledge_block": knowledge_block,
                "web_search_block": web_search_block,
                "executor_hint": executor_hint,
            },
        )
        return "FAKE_ANSWER"


def test_answer_agent_v6_class_can_be_instantiated_alone():
    """AnswerAgent 能脱离 service 单独实例化，且自带角色配置 / 指令 / 内部执行器。"""
    from agents.answer_agent import AnswerAgent
    from agents.answer_agent.llm_exec import _AgnoLlmZhixingQi

    a = AnswerAgent()
    assert isinstance(a, AnswerAgent)
    assert a.JIESHE and "最终回答负责人" in a.JIESHE
    assert a.ZHIDAO and "Final Answer" in a.ZHIDAO
    assert a.mingzi == "answer_agent"
    # 默认内部执行器是吸收后的 LLM 执行器（不是独立 agent）
    assert isinstance(a.zhixing, _AgnoLlmZhixingQi)


def test_answer_agent_v6_class_pan_and_huida_are_self_owned():
    """AnswerAgent.pan 自己产出 HuidaPan；huida 调用注入的 fake 执行器，hint 由 answer 自己写。"""
    from agents.answer_agent import AnswerAgent, HuidaPan
    from agents.main_agent import MainAgent
    from agents.middle_agent import MiddleAgent

    m = MainAgent()
    plan = m.pan("你好", session_id=None, http_use_knowledge=False, clock=BudgetClock.start()).plan
    mid = MiddleAgent()
    bundle = mid.caipan("你好", plan=plan, http_use_knowledge=False, clock=BudgetClock.start()).bundle

    fake = _FakeZhixing()
    a = AnswerAgent(zhixing=fake)
    hp = a.pan(plan, bundle)
    assert isinstance(hp, HuidaPan)
    # answer 自己签字 lane / primary_path（service 不再代写）
    assert hp.lane == "agno_basic"
    assert hp.primary_path == "agno_basic"
    assert hp.da_fengshi == "zhijie"

    text, hp2 = a.huida("你好", context_block=None, plan=plan, bundle=bundle, clock=BudgetClock.start())
    assert text == "FAKE_ANSWER"
    assert hp2.lane == hp.lane and hp2.primary_path == hp.primary_path
    # answer 把策略写进 hint 后才把执行权交给内部执行器
    assert fake.calls and "[answer]" in (fake.calls[0]["executor_hint"] or "")
    assert "[main]" in (fake.calls[0]["executor_hint"] or "")
    assert "[middle]" in (fake.calls[0]["executor_hint"] or "")


def test_answer_agent_v6_class_kb_weak_triggers_baoshou(monkeypatch):
    """弱知识场景：answer 自己把保守维度写进 hint，不依赖 service。

    V14 架构变化说明：
    - V14 retrieve_knowledge 使用独立的 rag.retriever.retrieve，不经 agno_rag_service
    - 必须同时 mock V14 的 rag.retriever.retrieve 才能触发 no_match → baoshou
    - 这是 V6 保守边界的有效验收：KB 完全无结果 → V14 no_match=True → da_fengshi=baoshou
    """
    from agents.answer_agent import AnswerAgent
    from agents.main_agent import MainAgent
    from agents.middle_agent import MiddleAgent

    # 同时 mock service 层和 V14 底层检索
    monkeypatch.setattr(
        "services.capabilities.knowledge.rag_orchestration_service.fetch_knowledge_block",
        lambda q, top_k=5: "",
    )
    monkeypatch.setattr(
        "services.capabilities.knowledge.rag_orchestration_service.fetch_knowledge_chunks",
        lambda q, top_k=5: [],  # V12 层返回空
    )
    # V14 底层检索也返回空（触发 no_match=True）
    monkeypatch.setattr(
        "rag.retrieve_knowledge_core._retrieve_keyword",
        lambda query, top_k=5, filters=None: [],
    )
    monkeypatch.setattr(
        "services.capabilities.web.web_orchestration_service.fetch_web_evidence_block",
        lambda q, max_results=3: "",
    )
    m = MainAgent()
    plan = m.pan("项目代号是什么？", session_id=None, http_use_knowledge=True, clock=BudgetClock.start()).plan
    mid = MiddleAgent()
    bundle = mid.caipan("项目代号是什么？", plan=plan, http_use_knowledge=True, clock=BudgetClock.start()).bundle

    fake = _FakeZhixing()
    a = AnswerAgent(zhixing=fake)
    text, hp = a.huida(
        "项目代号是什么？",
        context_block=None,
        plan=plan,
        bundle=bundle,
        clock=BudgetClock.start(),
    )
    # V15：retrieved_chunks 为空时 Answer 不进行 knowledge_block fallback，不向 LLM 注入伪证据
    assert not fake.calls, "无检索片段时不应调用内部执行器 shengcheng"
    assert "检索" in text or "片段" in text or "知识库" in text, (
        "无检索结果时应确定性说明，而非假装已命中："
        + str(text)[:200]
    )
    # KB 完全无结果 → V14 no_match=True → da_fengshi 应为 baoshou（保守边界）
    assert hp.da_fengshi == "baoshou", \
        f"KB 无结果时 da_fengshi 应为 baoshou（V14 no_match 保守路径），实际: {hp.da_fengshi}"


def test_knowledge_grounded_empty_chunks_uses_web_block():
    """KB 空但有 round1 web_block 时，Answer 应调用执行器而非模板短路。"""
    from dataclasses import replace

    from agents.answer_agent import AnswerAgent
    from agents.main_agent import MainAgent
    from agents.middle_agent import MiddleAgent

    m = MainAgent()
    plan = m.pan(
        "请比较 Keyword 检索和向量检索",
        session_id=None,
        http_use_knowledge=True,
        clock=BudgetClock.start(),
    ).plan
    plan = replace(plan, answer_mode="knowledge_grounded", needs_retrieval=True)
    mid = MiddleAgent()
    bundle = mid.caipan(
        "请比较 Keyword 检索和向量检索",
        plan=plan,
        http_use_knowledge=True,
        clock=BudgetClock.start(),
    ).bundle
    bundle = replace(
        bundle,
        retrieved_chunks=[],
        web_block="[Web检索] Hybrid 检索结合关键词与向量召回。",
    )

    fake = _FakeZhixing()
    a = AnswerAgent(zhixing=fake)
    text, _hp = a.huida(
        "请比较 Keyword 检索和向量检索",
        context_block=None,
        plan=plan,
        bundle=bundle,
        clock=BudgetClock.start(),
    )
    assert text == "FAKE_ANSWER"
    assert len(fake.calls) == 1
    assert fake.calls[0]["knowledge_block"] is None
    assert "Hybrid" in (fake.calls[0]["web_search_block"] or "")
