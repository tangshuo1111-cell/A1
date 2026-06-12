"""
Agno 基础问答 service（monkeypatch 锚点 / facade）。

本模块只做 **胶水 / 承接 / 协调** 三件事——

- 接 HTTP 请求
- 管 session / history
- 把请求依次交给 `MainAgent → MiddleAgent → AnswerAgent`
- 透传 answer extra，并由 chat 主链统一收口最终 lane / primary_path

主判断 **全部** 由三强 agent 实体在自身主入口里产出；
本模块 **不得** 再做协作方向、材料充分性、最终回答策略的任何主判断。

约束：只 import 三强**实体类**，不 deep-import 各自的 prompt 常量 / 内部 helper /
内部判断函数；schema dataclass 仅在类型注解层出现（透传容器）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from agents.answer_agent import AnswerAgent
from agents.main_agent import MainAgent
from agents.middle_agent import MiddleAgent
from application.chat.budget_clock import BudgetClock
from application.chat.run_chat_turn import ChatTurnDeps, run_agno_chat_turn_impl
from schemas import ChatTurnResult
from services.capabilities.web import web_orchestration_service as agno_web_service
from services.session_store import get_session_store

if TYPE_CHECKING:  # 仅类型注解用；service 不依赖这些 schema 的内部字段
    from schemas import MainDecision

_MAX_PAIRS = 6

# ---------------------------------------------------------------------------
# 三强实体单例：service 不再"代写"主判断对象，只持有三个 agent 实体并按链路串联。
# 它们都是 **可单独实例化** 的 agent 类。
# ---------------------------------------------------------------------------
_main_agent_inst: MainAgent = MainAgent()
_middle_agent_inst: MiddleAgent = MiddleAgent()
_answer_agent_inst: AnswerAgent = AnswerAgent()


# 以下 `_v4_*` 仅为「轨迹观测/指纹」工具，**不参与决策**：
# 路由/材料门控由 main / middle 决定；指纹只是 trace 的一个聚合视图。
def _v4_route_label(message: str, *, use_knowledge: bool) -> str:
    """与 middle 中 `_agno_route_label` 对齐，仅做指纹聚合，不做决策。"""
    msg = (message or "").strip()
    if use_knowledge:
        return "knowledge_first"
    if agno_web_service.user_requests_web_search(msg):
        return "web_explicit"
    return "direct"


def _v4_path_fingerprint(
    message: str,
    *,
    use_knowledge: bool,
    knowledge_block: str | None,
    web_block: str | None,
) -> str:
    route = _v4_route_label(message, use_knowledge=use_knowledge)
    if route == "direct":
        return "v4fp:direct"
    if route == "web_explicit":
        return "v4fp:web_explicit_hit" if (web_block or "").strip() else "v4fp:web_explicit_empty"
    has_kb = bool((knowledge_block or "").strip())
    has_wb = bool((web_block or "").strip())
    if has_kb and not has_wb:
        return "v4fp:kb_only"
    if not has_kb and has_wb:
        return "v4fp:kb_miss_web_hit"
    if has_kb and has_wb:
        return "v4fp:kb_hit_plus_web"
    return "v4fp:kb_miss_web_empty"


def _v4_nodes_contract(collab_trace: list[str]) -> dict[str, str]:
    """从轨迹提炼节点契约（便于肉眼 / 断言核对真实参与）。"""
    joined = "|".join(collab_trace)
    rag = "called" if "v4:2_gather:rag_call" in joined else "skipped"
    web = "called" if "v4:2_gather:web_call" in joined else "skipped"
    if "v4:2_gather:rag_hit" in joined:
        rag_out = "hit"
    elif "v4:2_gather:rag_miss" in joined:
        rag_out = "miss"
    else:
        rag_out = "n/a"
    if "v4:2_gather:web_hit" in joined:
        web_out = "hit"
    elif "v4:2_gather:web_empty" in joined:
        web_out = "empty"
    else:
        web_out = "n/a"
    return {
        "rag_phase": rag,
        "rag_outcome": rag_out,
        "web_phase": web,
        "web_outcome": web_out,
    }


def _gather_materials_v4(
    message: str,
    *,
    use_knowledge: bool,
) -> tuple[str | None, str | None, list[str]]:
    """兼容旧单测探针名：内部已切到 MainAgent → MiddleAgent 真协作（不替它们做主判断）。"""
    clock = BudgetClock.start()
    plan = _main_agent_inst.pan(
        message,
        session_id=None,
        http_use_knowledge=use_knowledge,
        clock=clock,
    ).plan
    bundle = _middle_agent_inst.caipan(
        message,
        plan=plan,
        http_use_knowledge=use_knowledge,
        clock=clock,
    ).bundle
    return bundle.knowledge_block, bundle.web_block, bundle.trace


def run_basic_qa(
    user_message: str,
    *,
    context_block: str | None = None,
    knowledge_block: str | None = None,
    web_search_block: str | None = None,
    main_decision: MainDecision | None = None,
    collaboration_plan: object | None = None,
    material_bundle: object | None = None,
    clock: BudgetClock,
    **_: Any,
) -> str:
    """胶水承接：把已就位的 plan / bundle 直接交给 `AnswerAgent.huida` 主入口。

    本函数 **不再做任何决策**，只把对象转交给 answer 实体。
    保留它的目的仅是兼容已有单测里的 `monkeypatch.setattr(services.agno_chat_service, "run_basic_qa", ...)`。
    """
    if main_decision is None or collaboration_plan is None or material_bundle is None:
        raise ValueError(
            "V6: run_basic_qa 需要 main_decision、collaboration_plan、material_bundle"
            "（请通过 run_agno_chat_turn 调用）",
        )
    text, _hp = _answer_agent_inst.huida(
        user_message,
        context_block=context_block,
        plan=collaboration_plan,  # type: ignore[arg-type]
        bundle=material_bundle,  # type: ignore[arg-type]
        clock=clock,
    )
    return text


def run_agno_chat_turn(
    message: str,
    *,
    session_id: str | None,
    request_id: str | None = None,
    use_knowledge: bool = False,
    v13_file_content: str | bytes | None = None,
    v13_text_content: str | None = None,
    v13_title: str | None = None,
    confirm_long_web_video_asr: bool = False,
) -> ChatTurnResult:
    """主链胶水：MainAgent.pan → MiddleAgent.caipan → AnswerAgent.huida。

    本函数 **不写** 任何主判断逻辑：
    - 协作方向 / 是否补 kb / 是否补 web → MainAgent 自己决定
    - 材料够不够 / 缺什么 / 下一步建议 → MiddleAgent 自己决定
    - 怎么对用户说 / answer 视角标签 / extra 字段 → AnswerAgent 自己决定

    可选参数：
    - v13_file_content: 前端上传的文件内容（bytes 或 str），触发文件 prepare 链路
    - v13_text_content: 直接文本内容（prepare_text 场景，可能不同于 message）
    - v13_title: 文本标题（可选）
    - confirm_long_web_video_asr: 用户在长网页视频（超过免确认秒数）上已确认走 ASR，
      与 ``video.web_video_chat_context.web_video_long_asr_confirmed`` 对齐，供 Middle 拉流时读取。

    实现迁至 ``application.chat.turn_orchestrator``；本符号仍为 service / 路由锚点。
    """
    session_key = _history_key(session_id)
    store = get_session_store()
    store.ensure_session(session_key)
    deps = ChatTurnDeps(
        histories=store.histories,
        session_prev_video=store.session_prev_video,
        session_pending_video=store.session_pending_video,
        lock=store.lock,
        main_agent=_main_agent_inst,
        middle_agent=_middle_agent_inst,
        answer_agent=_answer_agent_inst,
        run_basic_qa=run_basic_qa,
        path_fingerprint=_v4_path_fingerprint,
        nodes_contract=_v4_nodes_contract,
        max_history_pairs=_MAX_PAIRS,
    )
    # 整轮维度设置「长视频 ASR 已确认」ContextVar：fast / complex / 后台 各路径都能读到，
    # 不再局限于 _run_middle_stage（否则 fast 路径处理视频时拿不到确认标志）。
    from video.web_video_chat_context import web_video_long_asr_confirmed

    _wvac_tok = web_video_long_asr_confirmed.set(bool(confirm_long_web_video_asr))
    try:
        return run_agno_chat_turn_impl(
            message,
            session_id=session_id,
            request_id=request_id,
            use_knowledge=use_knowledge,
            v13_file_content=v13_file_content,
            v13_text_content=v13_text_content,
            v13_title=v13_title,
            confirm_long_web_video_asr=confirm_long_web_video_asr,
            deps=deps,
        )
    finally:
        store.persist_session(session_key)
        web_video_long_asr_confirmed.reset(_wvac_tok)


def _history_key(session_id: str | None) -> str:
    """会话 dict 键（与 application 层逻辑对齐；仅供本模块 clear_* 使用）。"""
    return (session_id or "").strip() or "__default__"


def clear_agno_session_history_for_tests() -> None:
    get_session_store().clear_all()


def clear_agno_session_prev_video_for_tests(session_id: str | None) -> None:
    """仅清掉某个 session 的视频锚点，**保留** _histories 原文（测试用）。

    用途（仅给"关键词碰撞强对照"测试用）：
    在同一会话里制造"前文原文还在 + 结构化锚点已无"的状态，验证系统不会
    被"刚才那个视频"这种字面指代骗到——它只在结构化锚点真存在时才承接。
    生产路径不会调这个函数。
    """
    key = _history_key(session_id)
    store = get_session_store()
    with store.lock:
        store.session_prev_video.pop(key, None)
