"""V1：Agno 基础问答新链（不经旧 LangGraph workflow）。

运行方式（仓库根执行，保证能定位到 `api` / `agents` / `services`）：
  python -m pytest tests/integration/test_agno_chat.py -q
"""

from __future__ import annotations

import sys

from tests._support.bootstrap import bootstrap_historical_test

REPO_ROOT = bootstrap_historical_test(__file__)
MAIN_CORE_DIR = REPO_ROOT.resolve()

# 两次 insert(0) 时，后插入的在最前。要求最终顺序：**01_主链核心** 在 sys.path 最前，
# 仓库根次之（以便 `config` / `core` 等）。做法：**先插入 REPO_ROOT，再插入 MAIN_CORE_DIR**。
for p in (str(REPO_ROOT), str(MAIN_CORE_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

import pytest
from fastapi.testclient import TestClient

from agents.agno_chat_agent import reset_agent_cache_for_tests
from api.main import app
from services import agno_chat_service


def disable_fast_lane_shortcuts(monkeypatch: pytest.MonkeyPatch) -> None:
    from config import feature_flags

    for flag in feature_flags.LANE_FAST_FLAG.values():
        monkeypatch.setitem(feature_flags.FEATURE_FLAGS, flag, False)


@pytest.fixture(autouse=True)
def _reset_agno_state(monkeypatch: pytest.MonkeyPatch) -> None:
    disable_fast_lane_shortcuts(monkeypatch)
    agno_chat_service.clear_agno_session_history_for_tests()
    reset_agent_cache_for_tests()
    yield
    agno_chat_service.clear_agno_session_history_for_tests()
    reset_agent_cache_for_tests()


def test_chat_agno_route_ok_without_old_workflow(monkeypatch: pytest.MonkeyPatch) -> None:
    """新路由可通；响应带来自新链标识，不经旧 chat_service.run_chat_turn。"""

    def fake_turn(
        message: str,
        *,
        session_id: str | None,
        request_id: str | None = None,
        use_knowledge: bool = False,
        **_extra: object,
    ) -> dict:
        return {
            "ok": True,
            "answer": f"mock:{message}",
            "session_id": session_id,
            "request_id": request_id,
            "answer_type": "basic_agno",
            "primary_path": "agno_basic",
            "pipeline_ok": True,
            "extra": {"lane": "agno_basic"},
        }

    monkeypatch.setattr(
        "services.agno_chat_service.run_agno_chat_turn",
        fake_turn,
    )
    with TestClient(app) as client:
        r = client.post("/chat/agno", json={"message": "你好", "session_id": "t-agno"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["answer"] == "mock:你好"
    assert body.get("primary_path") == "agno_basic"


def test_openapi_lists_chat_agno_route() -> None:
    """OpenAPI 中可见 POST /chat/agno，避免「有文件但路由未注册」。"""
    with TestClient(app) as client:
        r = client.get("/openapi.json")
    assert r.status_code == 200
    paths = r.json().get("paths", {})
    assert "/chat/agno" in paths
    assert "post" in paths["/chat/agno"]


def test_agno_chat_second_turn_includes_prior_context(monkeypatch: pytest.MonkeyPatch) -> None:
    """简单连续追问：第二轮应带上第一轮摘录（由 service 拼 context_block）。"""
    from config import feature_flags

    monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_COMPLEX_REFINE_V2", False)
    calls: list[tuple[str, str | None, str | None, str | None]] = []

    def fake_basic(
        user_message: str,
        *,
        context_block: str | None = None,
        knowledge_block: str | None = None,
        web_search_block: str | None = None,
        **_extra: object,
    ) -> str:
        calls.append((user_message, context_block, knowledge_block, web_search_block))
        return "ok"

    monkeypatch.setattr("services.agno_chat_service.run_basic_qa", fake_basic)
    agno_chat_service.run_agno_chat_turn("第一轮问题", session_id="sess-1")
    agno_chat_service.run_agno_chat_turn("那刚才呢？", session_id="sess-1")
    assert len(calls) == 2
    assert calls[0][1] is None
    assert calls[1][1] is not None
    assert "第一轮问题" in (calls[1][1] or "")
    assert calls[0][2] is None
    assert calls[1][2] is None
    assert calls[0][3] is None
    assert calls[1][3] is None


def test_agno_chat_service_isolated_from_chat_service() -> None:
    """防伪入口：agno_chat_service 未加载旧对话服务模块。"""
    import services.agno_chat_service as mod

    assert "chat_service" not in mod.__dict__
    assert "async_chat_service" not in mod.__dict__
    assert "workflow" not in mod.__dict__
