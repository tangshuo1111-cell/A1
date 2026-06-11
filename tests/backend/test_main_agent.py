import uuid
from datetime import UTC, datetime

from agents import main_agent
from application.chat.budget_clock import BudgetClock
from entry.task_dispatcher import dispatch_task
from schemas import TaskInput


def _task(q: str, *, session_id: str | None = None, ctx: str = "") -> TaskInput:
    return TaskInput(
        task_id=str(uuid.uuid4()),
        user_query=q,
        clean_query=q.strip(),
        has_link=False,
        link_urls=[],
        is_followup=False,
        session_id=session_id,
        created_at=datetime.now(UTC),
        context_snippet=ctx,
    )


def test_main_agent_routes_greeting_without_rag():
    t = dispatch_task("你好", session_id=None)
    t = t.model_copy(update={"context_snippet": ""})
    d = main_agent.decide(t)
    assert d.need_rag is False
    assert d.router_source == "rules"
    assert d.middle_collect_priority in ("balanced", "rag_first", "local_first", "http_first")


def test_main_agent_routes_kb_question_with_rag():
    t = _task("项目代号是什么")
    d = main_agent.decide(t)
    assert d.need_rag is True
    assert d.primary_goal


def test_main_agent_general_question_goes_direct():
    t = _task("如何打开易拉罐")
    d = main_agent.decide(t)
    assert d.need_rag is False
    assert d.answer_channel == "direct"


def test_main_agent_link_without_doc_scope_goes_external():
    t = TaskInput(
        task_id=str(uuid.uuid4()),
        user_query="看看 https://example.com/foo",
        clean_query="看看 https://example.com/foo",
        has_link=True,
        link_urls=["https://example.com/foo"],
        is_followup=False,
        session_id=None,
        created_at=datetime.now(UTC),
        context_snippet="",
    )
    d = main_agent.decide(t)
    assert d.answer_channel == "external"
    assert d.need_rag is False
    assert d.need_external_info is True


# ---------------------------------------------------------------------------
# V6 第 5 轮：MainAgent 已收成「可单独实例化 / 单独调用 / 单独测试」的协作判断 Agent。
# 这一组测试不依赖任何 service / answer / middle，只断言 MainAgent 自身能产出主判断对象。
# ---------------------------------------------------------------------------
def test_main_agent_v6_class_can_be_instantiated_alone():
    """MainAgent 能脱离 service 单独实例化，且自带角色配置 / 指令。"""
    from agents.main_agent import MainAgent

    m = MainAgent()
    assert isinstance(m, MainAgent)
    assert m.JIESHE and "协作总判断者" in m.JIESHE
    assert m.ZHIDAO and "证据" in m.ZHIDAO
    assert m.mingzi == "main_agent"


def test_main_agent_v6_class_pan_is_self_owned_plan():
    """MainAgent.pan 是单一主入口，主判断对象由 MainAgent 自己产出。"""
    from agents.main_agent import AgnoCollaborationPlan, MainAgent, MainXiezuoPan

    m = MainAgent()
    plan = m.pan("你好", session_id=None, http_use_knowledge=False, clock=BudgetClock.start()).plan
    assert isinstance(plan, AgnoCollaborationPlan)
    assert isinstance(plan.xiezuo_pan, MainXiezuoPan)
    # 直答场景：main 自己判断不需要证据 / 不允许 kb / 不允许 web
    assert plan.xiezuo_pan.renwu_lei == "zhijie"
    assert plan.xiezuo_pan.allow_kb is False
    assert plan.xiezuo_pan.allow_web is False
    assert plan.force_skip_evidence is True
    assert plan.execution_plan is not None
    assert plan.execution_plan.deadline_ms == 20000
    assert any(agent.name == "memory" for agent in plan.execution_plan.agents)


def test_main_agent_v6_class_kb_path_changes_pan():
    """换一种问题（带知识库意图），MainAgent 自身判断必须随之改变（主权真实存在）。"""
    from agents.main_agent import MainAgent

    m = MainAgent()
    plan = m.pan("项目代号是什么", session_id=None, http_use_knowledge=True, clock=BudgetClock.start()).plan
    assert plan.xiezuo_pan.allow_kb is True
    assert plan.xiezuo_pan.renwu_lei == "zhishu"
    assert plan.force_skip_evidence is False
    assert plan.execution_plan is not None
    assert any(agent.name == "kb" for agent in plan.execution_plan.agents)
