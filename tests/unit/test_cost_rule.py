"""config.cost_rule：环境变量覆盖与默认值（每测独立 reload，避免模块级 COST 串联）。"""

from __future__ import annotations

import importlib
import sys

import pytest
from tests._support.bootstrap import find_repo_root

REPO_ROOT = find_repo_root(__file__)
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _reload_cr() -> None:
    import config.cost_rule as m

    importlib.reload(m)


@pytest.fixture(autouse=True)
def _clean_cost_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "MAX_OUTPUT_CHARS",
        "RAG_MAX_TOP_K",
        "TOOL_MAX_STEPS",
        "WEB_FETCH_MAX_PAGES",
        "MAX_ESTIMATED_COST_USD",
        "AI_MAX_INPUT_CHARS",
    ):
        monkeypatch.delenv(key, raising=False)
    yield
    for key in (
        "MAX_OUTPUT_CHARS",
        "RAG_MAX_TOP_K",
        "TOOL_MAX_STEPS",
        "WEB_FETCH_MAX_PAGES",
        "MAX_ESTIMATED_COST_USD",
        "AI_MAX_INPUT_CHARS",
    ):
        monkeypatch.delenv(key, raising=False)
    _reload_cr()


def test_max_output_chars_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAX_OUTPUT_CHARS", "777")
    _reload_cr()
    from config.cost_rule import COST

    assert COST.max_output_chars == 777


def test_rag_max_top_k_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RAG_MAX_TOP_K", "3")
    _reload_cr()
    from config.cost_rule import COST

    assert COST.rag_max_top_k == 3


def test_tool_max_steps_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOOL_MAX_STEPS", "2")
    _reload_cr()
    from config.cost_rule import COST

    assert COST.tool_max_steps == 2


def test_web_fetch_max_pages_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEB_FETCH_MAX_PAGES", "1")
    _reload_cr()
    from config.cost_rule import COST

    assert COST.web_fetch_max_pages == 1


def test_max_estimated_cost_usd_env_float(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAX_ESTIMATED_COST_USD", "0.12")
    _reload_cr()
    from config.cost_rule import COST

    assert abs(COST.max_estimated_cost_usd - 0.12) < 1e-9


def test_invalid_env_falls_back_to_default_int(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_MAX_INPUT_CHARS", "not-a-number")
    _reload_cr()
    from config.cost_rule import COST

    assert COST.ai_max_input_chars == 16000
