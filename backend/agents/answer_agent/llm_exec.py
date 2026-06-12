"""
answer_agent 内部 LLM 执行器。

明确边界：
- 本文件 **不是** 独立 agent，只是 AnswerAgent 的内部组件。
- `_AgnoLlmZhixingQi.shengcheng` 是唯一对内调用面；策略已由 AnswerAgent 写进 `executor_hint`。
- 兼容旧 import：`agents.agno_chat_agent.run_basic_qa` 现作为薄壳转发到本模块的 `run_basic_qa`，
  保留既有 monkeypatch 钩子（测试 patch agno_chat_agent 仍生效）。
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from agno.agent import Agent
from agno.models.openai.like import OpenAILike

from application.chat.turn_cache import current_turn_cache
from config.settings import settings
from core.errors import AppError, ErrorCategory

from .prompt import ASSISTANT_INSTRUCTIONS

logger = logging.getLogger("light_maqa")
_ANSWER_LLM_METRICS_KEY = "answer_llm_metrics"


def _fake_llm_enabled() -> bool:
    return bool(settings.fake_llm_enabled)


def _require_llm_key() -> None:
    if not settings.openai_api_key:
        raise AppError(
            code="NO_LLM_KEY",
            message="未配置 LLM_API_KEY 或 OPENAI_API_KEY，无法使用 Agno 基础问答。",
            category=ErrorCategory.VALIDATION,
        )


@lru_cache(maxsize=1)
def _build_agent() -> Agent:
    _require_llm_key()
    model = OpenAILike(
        id=settings.default_llm_model,
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        timeout=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
    )
    return Agent(
        name="LightAssistant",
        model=model,
        instructions=ASSISTANT_INSTRUCTIONS,
        markdown=False,
        tools=[],
    )


def _estimate_tokens(text: str) -> int:
    value = str(text or "")
    if not value:
        return 0
    # Stable rough estimate for observability; avoids tokenizer dependency.
    ascii_chars = sum(1 for ch in value if ord(ch) < 128)
    non_ascii = max(0, len(value) - ascii_chars)
    return max(1, int(ascii_chars / 4) + int(non_ascii * 0.9))


def _record_answer_llm_metrics(
    *,
    prompt: str,
    answer_text: str,
    knowledge_block: str | None,
    web_search_block: str | None,
    executor_hint: str | None,
    usage: Any | None = None,
) -> None:
    cache = current_turn_cache()
    if cache is None:
        return
    metrics: dict[str, Any] = {
        "answer_llm.prompt_chars": len(prompt),
        "answer_llm.answer_chars": len(answer_text),
        "answer_llm.knowledge_chars": len((knowledge_block or "").strip()),
        "answer_llm.web_chars": len((web_search_block or "").strip()),
        "answer_llm.hint_chars": len((executor_hint or "").strip()),
        "answer_llm.prompt_tokens_est": _estimate_tokens(prompt),
        "answer_llm.answer_tokens_est": _estimate_tokens(answer_text),
    }
    if usage is not None:
        prompt_tokens = getattr(usage, "prompt_tokens", None)
        completion_tokens = getattr(usage, "completion_tokens", None)
        total_tokens = getattr(usage, "total_tokens", None)
        if prompt_tokens is not None:
            metrics["answer_llm.prompt_tokens"] = int(prompt_tokens)
        if completion_tokens is not None:
            metrics["answer_llm.answer_tokens"] = int(completion_tokens)
        if total_tokens is not None:
            metrics["answer_llm.total_tokens"] = int(total_tokens)
    cache.set(_ANSWER_LLM_METRICS_KEY, metrics, lane="general")


def load_answer_llm_metrics() -> dict[str, Any]:
    cache = current_turn_cache()
    if cache is None:
        return {}
    item = cache.get(_ANSWER_LLM_METRICS_KEY, lane="general")
    return dict(item) if isinstance(item, dict) else {}


def run_basic_qa(
    user_message: str,
    *,
    context_block: str | None = None,
    knowledge_block: str | None = None,
    web_search_block: str | None = None,
    executor_hint: str | None = None,
) -> str:
    """
    跑一轮基础问答，返回助手纯文本。

    注意：策略已由 AnswerAgent 写入 `executor_hint`；本函数 **不**再做任何材料/策略判断，
    仅按上下文/材料/策略提示组装 prompt 并调 LLM。
    """
    text = (user_message or "").strip()
    if not text:
        raise AppError(
            code="EMPTY_MESSAGE",
            message="消息不能为空",
            category=ErrorCategory.VALIDATION,
        )
    kb = (knowledge_block or "").strip()
    kb_prefix = ""
    if kb:
        kb_prefix = f"【参考材料】\n{kb}\n\n"
    web = (web_search_block or "").strip()
    web_prefix = ""
    if web:
        web_prefix = f"【网页补充】\n{web}\n\n"
    head = kb_prefix + web_prefix
    strat = ""
    if (executor_hint or "").strip():
        strat = f"【作答策略】\n{executor_hint.strip()}\n\n"
    output_rule = ""
    if kb or web:
        output_rule = (
            "【输出要求】\n"
            "先给结论；用自然段或短列表表达；不要复述题目或材料标题；"
            "不要用 --- / ### / **章节标题** 这类 markdown 模板；"
            "可保留 ✅ ⚠️ 📌 等轻量 emoji。\n\n"
        )
    if context_block:
        prompt = (
            strat
            + output_rule
            + head
            + "【会话摘录】\n"
            + f"{context_block.strip()}\n\n"
            + "【用户问题】\n"
            + f"{text}"
        )
    else:
        prompt = strat + output_rule + (head + f"【用户问题】\n{text}" if head else text)

    if _fake_llm_enabled():
        return f"测试回答：{text}"

    agent = _build_agent()
    try:
        resp = agent.run(prompt)
    except AppError:
        raise
    except Exception as e:  # noqa: BLE001
        logger.exception("agno basic qa failed")
        raise AppError(
            code="AGNO_RUN_FAILED",
            message="基础问答调用失败，请稍后重试。",
            category=ErrorCategory.LLM,
            details={"reason": str(e)},
        ) from e

    content = getattr(resp, "content", None)
    if isinstance(content, str) and content.strip():
        answer = content.strip()
        _record_answer_llm_metrics(
            prompt=prompt,
            answer_text=answer,
            knowledge_block=knowledge_block,
            web_search_block=web_search_block,
            executor_hint=executor_hint,
            usage=getattr(resp, "usage", None),
        )
        return answer
    msgs = getattr(resp, "messages", None)
    if msgs:
        last = msgs[-1]
        c2 = getattr(last, "content", None)
        if isinstance(c2, str) and c2.strip():
            answer = c2.strip()
            _record_answer_llm_metrics(
                prompt=prompt,
                answer_text=answer,
                knowledge_block=knowledge_block,
                web_search_block=web_search_block,
                executor_hint=executor_hint,
                usage=getattr(resp, "usage", None),
            )
            return answer
    raise AppError(
        code="AGNO_EMPTY_RESPONSE",
        message="模型未返回有效文本",
        category=ErrorCategory.LLM,
    )


def reset_agent_cache_for_tests() -> None:
    """测试用：清掉 Agent 单例。"""
    _build_agent.cache_clear()


class _AgnoLlmZhixingQi:
    """
    answer 的内部 LLM 执行器（V6 已吸收 agno_chat_agent 的执行能力）。

    本类不再是独立 agent；它只负责按 answer 给出的 hint 调用底层 LLM 文本生成。
    可在测试中用注入替换，避免触发真实 LLM Key。

    主入口：`shengcheng(...)`（"生成"），唯一对内调用面。
    """

    MINGZI: str = "agno_llm_zhixing_qi"

    def shengcheng(
        self,
        user_message: str,
        *,
        context_block: str | None,
        knowledge_block: str | None,
        web_search_block: str | None,
        executor_hint: str | None,
    ) -> str:
        # 走 `agents.agno_chat_agent.run_basic_qa`（薄壳）以保留既有 monkeypatch 钩子；
        # 该薄壳已被收口为本模块 `run_basic_qa` 的转发，不会做任何策略决策。
        from agents import agno_chat_agent

        return agno_chat_agent.run_basic_qa(
            user_message,
            context_block=context_block,
            knowledge_block=knowledge_block,
            web_search_block=web_search_block,
            executor_hint=executor_hint,
        )
