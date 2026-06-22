"""
用 LLM 辅助主路由（JSON 输出），失败则回退规则结果。

在 `MainAgentRuntime.shibie_yitu` 三段式判断里复用的 **纯意图分类**
函数 `classify_intent_with_llm`（不和 decision-merge 路径耦合；
MainAgentRuntime 自产 decision，不调 legacy.decide）。

【边界】仅路由/分类，不生成最终用户回答；不接远端 MCP。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from config.settings import settings
from schemas import MainDecision, TaskInput


class _LLMRouterOut(BaseModel):
    """LLM 必须返回的可解析子集（多余字段忽略）。"""

    need_rag: bool = True
    need_context: bool = False
    need_external_info: bool = False
    need_tool_local: bool = False
    primary_goal: str = Field(default="", description="用户主目标短句")
    is_compound: bool = False
    middle_collect_priority: str = Field(
        default="balanced",
        description="balanced | rag_first | local_first | http_first",
    )
    answer_style: str = Field(
        default="general",
        description="general | explain | steps | compare | conclusion",
    )
    answer_style_hint: str = Field(
        default="",
        description="给 answer 的中文风格提示；可空，由 merge 用 answer_style 兜底生成",
    )
    routing_explain: str = Field(
        default="",
        description="中文一句：为何如此设置 need_* / 优先级 / 风格（主判断核心说明）",
    )
    middle_agent_instruction: str = ""
    task_status: str = "routed"

    @field_validator("middle_collect_priority")
    @classmethod
    def _prio(cls, v: str) -> str:
        allowed = {"balanced", "rag_first", "local_first", "http_first"}
        return v if v in allowed else "balanced"

    @field_validator("answer_style")
    @classmethod
    def _style(cls, v: str) -> str:
        allowed = {"general", "explain", "steps", "compare", "conclusion"}
        return v if v in allowed else "general"


def _extract_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        raise ValueError("no json object in llm output")
    return json.loads(m.group(0))


def _hint_from_style(style: str, compound: bool) -> str:
    """与 main_agent 规则侧一致的风格提示兜底（避免 router 依赖 main_agent 循环导入）。"""
    hints = {
        "explain": "用概念解释型结构：先定义/直觉，再引用依据，避免堆砌术语。",
        "steps": "用步骤型结构：按顺序列要点；若证据无明确步骤，标明并退化为要点列表。",
        "compare": "用对比型结构：分维度对照；缺对立面信息时要写明缺口。",
        "conclusion": "先给收敛结论，再列依据，最后补充限制条件。",
        "general": "结论—依据—补充说明三段式；证据偏弱时降低确信度。",
    }
    base = hints.get(style, hints["general"])
    return base + " 本题可能为复合问，尽量分点覆盖子问题。" if compound else base


def merge_llm_into_decision(
    task: TaskInput,
    base: MainDecision,
    raw: _LLMRouterOut,
) -> MainDecision:
    """轻规则兜底：寒暄类不允许被 LLM 强行开检索。"""
    hint = raw.answer_style_hint.strip() or _hint_from_style(
        raw.answer_style, raw.is_compound
    )
    # 若规则侧已关检索（极短寒暄），保持关检索，但可采纳 instruction 的温和部分
    if not base.need_rag and not base.need_external_info and not base.need_tool_local:
        return base.model_copy(
            update={
                "primary_goal": raw.primary_goal or base.primary_goal,
                "is_compound": raw.is_compound,
                "answer_style": raw.answer_style,
                "answer_style_hint": hint,
                "routing_explain": (raw.routing_explain or "").strip(),
                "router_source": "hybrid",
                "llm_error": "",
                "answer_channel": base.answer_channel,
            }
        )
    return base.model_copy(
        update={
            "need_rag": raw.need_rag,
            "need_context": raw.need_context or base.need_context,
            "need_external_info": raw.need_external_info,
            "need_tool_local": raw.need_tool_local,
            "middle_agent_instruction": (
                raw.middle_agent_instruction or base.middle_agent_instruction
            ),
            "primary_goal": raw.primary_goal or base.primary_goal,
            "is_compound": raw.is_compound,
            "middle_collect_priority": raw.middle_collect_priority,
            "answer_style": raw.answer_style,
            "answer_style_hint": hint,
            "routing_explain": (raw.routing_explain or "").strip(),
            "task_status": raw.task_status or "routed",
            "router_source": "llm",
            "llm_error": "",
            "answer_channel": base.answer_channel,
        }
    )


def maybe_refine_with_llm(task: TaskInput, base: MainDecision) -> MainDecision:
    """
    若配置了 API Key 且 provider 为 openai 兼容，则调用一次 chat.completions，否则直接返回 base。
    """
    if not settings.llm_effective_for_router:
        return base.model_copy(update={"router_source": "rules"})

    try:
        from openai import OpenAI  # type: ignore[import-untyped]
    except ImportError:
        return base.model_copy(
            update={"router_source": "rules", "llm_error": "openai 包未安装"}
        )

    sys_prompt = (
        "你是轻量多 Agent 问答系统的主路由模块。只输出 JSON，不要 Markdown。"
        "根据用户问题与会话摘要，判断需要哪些资料渠道。"
        "字段：need_rag,need_context,need_external_info,need_tool_local(bool),"
        "primary_goal(str),is_compound(bool),"
        "middle_collect_priority(balanced|rag_first|local_first|http_first),"
        "answer_style(general|explain|steps|compare|conclusion),"
        "answer_style_hint(str,中文一句，指导最终回答语气/结构),"
        "routing_explain(str,中文一句，说明为何如此路由/开哪些渠道),"
        "middle_agent_instruction(str,中文简短),task_status(str)。"
        "need_tool_local：用户明确要读本地 knowledge_samples 下文件或列目录时为 true。"
        "need_external_info：问题含 http(s) 链接或明确要抓网页时为 true。"
    )
    user_block = (
        f"用户问题：{task.user_query}\n"
        f"清洗后：{task.clean_query}\n"
        f"has_link={task.has_link} link_urls={task.link_urls}\n"
        f"is_followup={task.is_followup}\n"
        f"会话摘要(可能为空)：\n{task.context_snippet[:6000]}\n"
        f"规则基线 need_rag={base.need_rag} need_external={base.need_external_info} "
        f"need_tool_local={base.need_tool_local} need_context={base.need_context}\n"
    )
    client = OpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        timeout=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
    )
    from config.cost_rule import COST
    from core.cost_recorder import get_accumulated_cost, record_llm_call

    if get_accumulated_cost() >= COST.max_estimated_cost_usd:
        return base.model_copy(
            update={"router_source": "rules", "llm_error": "cost_limit_reached"}
        )

    try:
        resp = client.chat.completions.create(
            model=settings.llm_router_model,
            # 路由判定用贪心解码（贪心=0.0）：同一输入跨次落到同一 lane/mode，
            # 收敛 KI-V1-001 的升级路径非确定性；与本文件其余路由调用（已 0.0）口径一致。
            temperature=0.0,
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_block},
            ],
        )
        content = (resp.choices[0].message.content or "").strip()
        usage = getattr(resp, "usage", None)
        in_tok = getattr(usage, "prompt_tokens", 0) or 0
        out_tok = getattr(usage, "completion_tokens", 0) or 0
        record_llm_call(settings.llm_router_model, in_tok, out_tok, 0.0)
        data = _extract_json_object(content)
        parsed = _LLMRouterOut.model_validate(data)
        return merge_llm_into_decision(task, base, parsed)
    except Exception as e:  # noqa: BLE001
        return base.model_copy(
            update={"router_source": "rules", "llm_error": f"llm_router_failed: {e!s}"}
        )


# ===========================================================================
# MainAgentRuntime 三段式判断专用 —— "纯意图分类" LLM 主判断
#
# 与 maybe_refine_with_llm() 的关键区别：
#   1) 输入只是一段自然语言 message（不依赖 TaskInput / MainDecision）
#   2) 输出只是一个意图字符串 + 置信度 + 理由（不动 MainDecision）
#   3) 由 MainAgentRuntime 在自家 shibie_yitu 内调用 → router_source 须保持
#      "main_agent_runtime"（测试与下游契约依赖此值）
#   4) 失败 / 不可用 / 输出无效都返回 LlmIntentResult.unavailable(...)，
#      让 MainAgentRuntime 自己决定走极少量高置信兜底
# ===========================================================================

# 主判断 4 类合法意图（与 MainAgentRuntime.shibie_yitu 完全对齐）
_VALID_INTENTS: frozenset[str] = frozenset({
    "zhijie_yitu",
    "zhishu_yitu",
    "waibu_yitu",
    "hunhe_yitu",
})


IntentLiteral = Literal["zhijie_yitu", "zhishu_yitu", "waibu_yitu", "hunhe_yitu"]


@dataclass(frozen=True)
class LlmIntentResult:
    """LLM 意图分类结果（不直接进 MainDecision，由 runtime 自己消费）。

    - `available=True` 且 `intent` 合法 → 主判断采用 LLM 结果
    - `available=False` 或 `intent` 无效 → 主判断进入 fallback（极少量高置信规则）
    - `reason` 是 LLM 自然语言理由（≤ 80 字，仅供 trace 可读）
    - `error` 是失败原因短串（仅 unavailable 时有意义）
    """

    available: bool
    intent: str = ""
    reason: str = ""
    error: str = ""

    @classmethod
    def ok(cls, intent: str, reason: str = "") -> LlmIntentResult:
        return cls(available=True, intent=intent, reason=reason[:80], error="")

    @classmethod
    def unavailable(cls, error: str) -> LlmIntentResult:
        return cls(available=False, intent="", reason="", error=error[:80])


class _IntentOnlyOut(BaseModel):
    """LLM 必须返回的最小可解析子集（多余字段忽略）。"""

    intent: str = Field(default="", description="zhijie_yitu/zhishu_yitu/waibu_yitu/hunhe_yitu")
    reason: str = Field(default="", description="中文短句：为什么这样判（≤ 80 字）")

    @field_validator("intent")
    @classmethod
    def _i(cls, v: str) -> str:
        s = (v or "").strip()
        return s if s in _VALID_INTENTS else ""


_INTENT_SYSTEM_PROMPT: str = (
    "你是「轻量多 Agent 问答系统」的主路由意图分类器。\n"
    "你只输出一个 JSON 对象，不要 Markdown，不要任何解释文字。\n"
    "字段：\n"
    "  intent: 必须是下列四种之一\n"
    "    - zhishu_yitu: 用户在问本项目/本仓库/知识库里有什么、是什么、做了什么、"
    "支持哪些能力、有哪些主题/文件/能力、项目代号、内部说明等可以从本地知识库取材的问题\n"
    "    - waibu_yitu: 用户明确想让你去外网/网页/搜索引擎查实时信息（天气、新闻、外站资讯等）\n"
    "    - hunhe_yitu: 既需要本地知识库材料、又需要外网实时信息，两者缺一不可\n"
    "    - zhijie_yitu: 寒暄/通识/与本项目无关的世界知识问答/简单计算/单纯指令性请求等"
    "无需任何外部材料就能回答\n"
    "  reason: 一句中文，≤ 80 字，简要说明为何如此判定\n"
    "判定原则：\n"
    "  - 用户问『知识库里有什么』/『项目代号』/『本仓库支持什么』/『本项目有哪些能力』 → zhishu_yitu\n"
    "  - 用户问『今天天气』/『上网查 X』/『搜一下 Y』/『去 X 网查』 → waibu_yitu\n"
    "  - 用户问『先查知识库再查网上』 → hunhe_yitu\n"
    "  - 一般寒暄、问候、通识闲聊、不涉及本项目的世界知识 → zhijie_yitu\n"
    "  - 拿不准时倾向 zhijie_yitu（保守），不要把日常问题强行送进知识库。\n"
)


def classify_intent_with_llm(
    message: str,
    *,
    timeout_seconds: float | None = None,
) -> LlmIntentResult:
    """主判断专用：把一段自然语言消息分类成 4 个主意图之一。

    设计边界（极简、可被 MainAgentRuntime 安全调用）：
    - 不依赖 TaskInput / MainDecision；不写 MainDecision；不修改任何全局状态
    - LLM 不可用（无 key / use_llm_router=0 / 非 openai 兼容）→ 返回 unavailable
    - LLM 调用失败 / 超时 / JSON 不可解析 / intent 字段无效 → 返回 unavailable
    - 调用方（MainAgentRuntime）拿到 unavailable 时进入"极少量高置信规则"兜底
    """
    msg = (message or "").strip()
    if not msg:
        return LlmIntentResult.unavailable("empty_message")
    if not settings.llm_effective_for_router:
        return LlmIntentResult.unavailable("llm_unavailable")

    try:
        from openai import OpenAI  # type: ignore[import-untyped]
    except ImportError:
        return LlmIntentResult.unavailable("openai_pkg_missing")

    from config.cost_rule import COST
    from core.cost_recorder import get_accumulated_cost, record_llm_call

    if get_accumulated_cost() >= COST.max_estimated_cost_usd:
        return LlmIntentResult.unavailable("cost_limit_reached")

    client = OpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        timeout=float(timeout_seconds) if timeout_seconds else settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
    )
    user_block = f"用户消息：{msg[:2000]}"
    try:
        resp = client.chat.completions.create(
            model=settings.llm_router_model,
            temperature=0.0,
            messages=[
                {"role": "system", "content": _INTENT_SYSTEM_PROMPT},
                {"role": "user", "content": user_block},
            ],
        )
        content = (resp.choices[0].message.content or "").strip()
        usage = getattr(resp, "usage", None)
        in_tok = getattr(usage, "prompt_tokens", 0) or 0
        out_tok = getattr(usage, "completion_tokens", 0) or 0
        record_llm_call(settings.llm_router_model, in_tok, out_tok, 0.0)
    except Exception as e:  # noqa: BLE001
        return LlmIntentResult.unavailable(f"llm_call_failed: {type(e).__name__}")

    try:
        data = _extract_json_object(content)
    except (ValueError, json.JSONDecodeError) as e:
        return LlmIntentResult.unavailable(f"json_parse: {e!s}")

    try:
        parsed = _IntentOnlyOut.model_validate(data)
    except (ValueError, TypeError) as e:
        return LlmIntentResult.unavailable(f"validation: {type(e).__name__}")

    if not parsed.intent:
        return LlmIntentResult.unavailable("invalid_intent")

    return LlmIntentResult.ok(parsed.intent, parsed.reason)


__all__ = [
    "IntentLiteral",
    "LlmIntentResult",
    "_LLMRouterOut",
    "classify_intent_with_llm",
    "classify_v13_intent_with_llm",
    "maybe_refine_with_llm",
    "merge_llm_into_decision",
]


# ===========================================================================
# 资料生命周期意图分类（prepare / commit / none）
#
# 设计原则：
# - 与主路由意图（zhijie/zhishu/waibu/hunhe）完全独立，不干扰原有四类意图
# - 仅当用户消息中含有明确的"资料提供"或"保存"行为信号时才触发
# - 失败 / LLM 不可用 → 返回 unavailable（上游走规则兜底）
# - 不接管主判断，只产出 v13_prepare_intent / v13_commit_intent 填充值
# ===========================================================================

# 资料生命周期合法意图集合（含视频 prepare 意图）
_V13_VALID_INTENTS: frozenset[str] = frozenset({
    "prepare_text",
    "prepare_file",
    "prepare_web_url",
    "prepare_local_video",   # 本地视频文件
    "prepare_web_video",     # 网页/视频站 URL
    "commit_pending",
    "none",      # 无资料 prepare/commit 相关意图（普通问题）
})

_V13_INTENT_SYSTEM_PROMPT: str = (
    "你是「轻量多 Agent 问答系统」的资料生命周期意图分类器。\n"
    "你只输出一个 JSON 对象，不要 Markdown，不要任何解释文字。\n"
    "字段：\n"
    "  intent: 必须是下列七种之一\n"
    "    - prepare_text: 用户粘贴/提供了一段较长文本，想让系统先解析/记录/备用，"
    "或说了类似'帮我记一下这段内容'/'把这段文本先放进待保存'/'先看看这段资料'等\n"
    "    - prepare_file: 用户提到了上传/拖入文件(.txt/.md等)，想让系统先解析/预览，"
    "或说了类似'我上传了一个txt'/'这个md文件先帮我看下'/'先别保存，看看文件'等\n"
    "    - prepare_web_url: 用户提供了一个 http/https URL 指向普通网页，想先抓取/预览正文，"
    "如'这个网页帮我抓一下'/'先读取这个链接'等（注意：视频URL走 prepare_web_video）\n"
    "    - prepare_local_video: 用户提到了一个本地视频文件路径(.mp4等)，"
    "想先提取/查看视频文本内容，如'这个视频帮我先看看'/'先看看这个mp4里说了什么'等\n"
    "    - prepare_web_video: 用户提供了一个视频网站URL(Bilibili/YouTube等)或带视频的链接，"
    "想先获取/查看视频字幕/内容，如'这个Bilibili视频先帮我看看'/'先提取这个视频的字幕'等\n"
    "    - commit_pending: 用户明确表达要把之前已解析的资料保存/入库/存入知识库，"
    "如'保存到知识库'/'把刚才那个存进去'/'确认保存'/'这个可以入库了'/'存起来'/'以后也要用'等\n"
    "    - none: 以上都不是，这是普通问答、知识检索、闲聊等，没有资料 prepare/commit 行为\n"
    "  source_type: 仅当 intent 为 prepare_* 时填写来源类型："
    "text / text_file / web_url / local_video / web_video；否则填空字符串\n"
    "  raw_source: 仅当 intent 为 prepare_web_url / prepare_file / prepare_local_video / prepare_web_video 时，"
    "填写 URL 或文件名；否则填空字符串\n"
    "  reason: 一句中文，≤ 80 字，简要说明为何如此判定\n"
    "判定原则：\n"
    "  - 用户只是在问一个问题（哪怕很长），没有明确提供资料 → none\n"
    "  - 用户提供了一段文本内容 + 想先看/先记/先备 → prepare_text\n"
    "  - 用户提到了文件(.txt/.md) + 想先看/先解析 → prepare_file\n"
    "  - 用户给了普通网页URL + 想先抓取/先预览 → prepare_web_url\n"
    "  - 用户给了本地视频路径(.mp4等) + 想看内容 → prepare_local_video\n"
    "  - 用户给了视频网站URL + 想看内容/字幕 → prepare_web_video\n"
    "  - 用户说'保存'/'入库'/'存进知识库' → commit_pending\n"
    "  - 拿不准时倾向 none（保守），不要把普通问题误判为 prepare\n"
)


@dataclass(frozen=True)
class V13IntentResult:
    """资料生命周期意图分类结果。

    - available=True + intent 合法 → 上游使用此结果填充 plan
    - available=False → 上游走规则兜底
    """

    available: bool
    intent: str = ""          # prepare_text / prepare_file / prepare_web_url / commit_pending / none
    source_type: str = ""     # text / text_file / web_url（prepare_* 时）
    raw_source: str = ""      # URL 或文件名（prepare_web_url / prepare_file 时）
    reason: str = ""
    error: str = ""

    @classmethod
    def ok(
        cls,
        intent: str,
        source_type: str = "",
        raw_source: str = "",
        reason: str = "",
    ) -> V13IntentResult:
        return cls(
            available=True,
            intent=intent,
            source_type=source_type,
            raw_source=raw_source,
            reason=reason[:80],
            error="",
        )

    @classmethod
    def unavailable(cls, error: str) -> V13IntentResult:
        return cls(available=False, intent="", error=error[:80])


class _V13IntentOut(BaseModel):
    """LLM 输出的可解析子集。"""

    intent: str = Field(default="none")
    source_type: str = Field(default="")
    raw_source: str = Field(default="")
    reason: str = Field(default="")

    @field_validator("intent")
    @classmethod
    def _i(cls, v: str) -> str:
        s = (v or "").strip()
        return s if s in _V13_VALID_INTENTS else "none"


def classify_v13_intent_with_llm(
    message: str,
    *,
    timeout_seconds: float | None = None,
) -> V13IntentResult:
    """把用户消息分类成资料生命周期意图（prepare_* / commit_pending / none）。

    设计边界：
    - 完全独立于主路由四类意图，不干扰原有 classify_intent_with_llm
    - LLM 不可用 / 失败 → 返回 unavailable，由上游走规则兜底
    - 只做"是否有资料 prepare/commit 行为"判断，不决定主判断
    """
    msg = (message or "").strip()
    if not msg:
        return V13IntentResult.unavailable("empty_message")
    if not settings.llm_effective_for_router:
        return V13IntentResult.unavailable("llm_unavailable")

    try:
        from openai import OpenAI  # type: ignore[import-untyped]
    except ImportError:
        return V13IntentResult.unavailable("openai_pkg_missing")

    client = OpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        timeout=float(timeout_seconds) if timeout_seconds else settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
    )
    user_block = f"用户消息：{msg[:2000]}"
    try:
        resp = client.chat.completions.create(
            model=settings.llm_router_model,
            temperature=0.0,
            messages=[
                {"role": "system", "content": _V13_INTENT_SYSTEM_PROMPT},
                {"role": "user", "content": user_block},
            ],
        )
        content = (resp.choices[0].message.content or "").strip()
    except Exception as e:  # noqa: BLE001
        return V13IntentResult.unavailable(f"llm_call_failed: {type(e).__name__}")

    try:
        data = _extract_json_object(content)
    except (ValueError, json.JSONDecodeError) as e:
        return V13IntentResult.unavailable(f"json_parse: {e!s}")

    try:
        parsed = _V13IntentOut.model_validate(data)
    except (ValueError, TypeError) as e:
        return V13IntentResult.unavailable(f"validation: {type(e).__name__}")

    return V13IntentResult.ok(
        intent=parsed.intent,
        source_type=parsed.source_type or "",
        raw_source=parsed.raw_source or "",
        reason=parsed.reason,
    )
