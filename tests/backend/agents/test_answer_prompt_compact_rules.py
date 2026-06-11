from __future__ import annotations

from agents.answer_agent import llm_exec
from application.chat.turn_cache import TurnCache, bind_turn_cache, reset_turn_cache


class _FakeResp:
    def __init__(self, content: str) -> None:
        self.content = content
        self.usage = None


class _FakeAgent:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def run(self, prompt: str) -> _FakeResp:
        self.prompts.append(prompt)
        return _FakeResp("ok")


def test_knowledge_grounded_prompt_includes_compact_output_rules(monkeypatch) -> None:
    # 本用例需走真实 _build_agent 路径以捕获 prompt，必须关掉 FAKE_LLM 短路。
    # 收口后 _fake_llm_enabled() 读 settings 单例（不再实时读 env），故 patch 配置项。
    monkeypatch.setattr(llm_exec.settings, "fake_llm_enabled", False)
    fake = _FakeAgent()
    monkeypatch.setattr(llm_exec, "_build_agent", lambda: fake)
    token = bind_turn_cache(TurnCache(request_id="t"))
    try:
        out = llm_exec.run_basic_qa(
            "请给我未来4周整改路线图",
            knowledge_block="材料1（A）：第一条证据\n\n材料2（B）：第二条证据",
            executor_hint="[answer] 用简体中文；先结论，再展开；尽量精炼，少重复材料原句。",
        )
        assert out == "ok"
        prompt = fake.prompts[-1]
        assert "【输出要求】" in prompt
        assert "先给结论" in prompt
        assert "少重复材料原句" in prompt
        assert "不要复述题目或材料标题" in prompt
    finally:
        reset_turn_cache(token)
