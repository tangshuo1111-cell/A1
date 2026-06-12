"""
Agno 基础问答的薄壳转发模块。

现状：
- 真正的运行时实现位于 `agents.answer_agent.llm_exec`，由 `AnswerAgent._AgnoLlmZhixingQi`
  作为 answer 的内部 LLM 执行器使用。
- 本文件仅做两件事：
  1) 转发 `from agents.agno_chat_agent import run_basic_qa` 等导入路径；
  2) 暴露 monkeypatch 钩子，让针对 `agents.agno_chat_agent.run_basic_qa` 的 patch 仍生效。
- `run_basic_qa` 只做底层文本生成，不做任何材料 / 策略判断。

禁止：从本模块再 import 任何已删除的旧主链符号（workflow / chat_service / async_chat_service / 等）。
"""

from __future__ import annotations

from agents.answer_agent.llm_exec import (  # noqa: F401
    _AgnoLlmZhixingQi,
    _build_agent,
    _require_llm_key,
    reset_agent_cache_for_tests,
    run_basic_qa,
)

# 模块级 docstring 已写死「不再以独立 agent 身份存在」；本文件不应再追加任何函数。
__all__ = [
    "run_basic_qa",
    "reset_agent_cache_for_tests",
]
