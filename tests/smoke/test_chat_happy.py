"""Smoke：/chat/agno 主链路 HTTP 层可通（不涉及真实 LLM）。"""

from __future__ import annotations

import sys

import pytest
from fastapi.testclient import TestClient
from tests._support.bootstrap import bootstrap_historical_test, find_repo_root

bootstrap_historical_test(__file__)
REPO_ROOT = find_repo_root(__file__)
for p in (str(REPO_ROOT), str(REPO_ROOT.resolve())):
    if p not in sys.path:
        sys.path.insert(0, p)

from agents.agno_chat_agent import reset_agent_cache_for_tests  # noqa: E402
from api.main import app  # noqa: E402
from services import agno_chat_service  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_agno_state() -> None:
    agno_chat_service.clear_agno_session_history_for_tests()
    reset_agent_cache_for_tests()
    yield
    agno_chat_service.clear_agno_session_history_for_tests()
    reset_agent_cache_for_tests()


def _fake_turn(message: str, *, session_id: str | None = None, **_kw: object) -> dict:
    """与真实 ``run_agno_chat_turn`` 一致：响应中的 session_id 回显请求侧。"""
    return {
        "ok": True,
        "answer": "pong",
        "session_id": session_id,
        "request_id": None,
        "answer_type": "basic_agno",
        "primary_path": "agno_basic",
        "pipeline_ok": True,
        "extra": {"lane": "agno_basic"},
    }


def test_chat_agno_returns_ok_true(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("services.agno_chat_service.run_agno_chat_turn", _fake_turn)
    with TestClient(app) as client:
        r = client.post("/chat/agno", json={"message": "ping", "session_id": "s1"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body.get("pipeline_ok") is True


def test_chat_agno_with_use_knowledge_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[bool] = []

    def capture(message: str, *, session_id, use_knowledge: bool = False, **_e: object) -> dict:
        calls.append(use_knowledge)
        return {**_fake_turn(message, session_id=session_id), "answer": "kb" if use_knowledge else "no"}

    monkeypatch.setattr("services.agno_chat_service.run_agno_chat_turn", capture)
    with TestClient(app) as client:
        r = client.post(
            "/chat/agno",
            json={"message": "hi", "session_id": "s2", "use_knowledge": True},
        )
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert calls == [True]


def test_chat_agno_preserves_session_id_in_response(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("services.agno_chat_service.run_agno_chat_turn", _fake_turn)
    with TestClient(app) as client:
        r = client.post("/chat/agno", json={"message": "x", "session_id": "client-sid-9"})
    assert r.status_code == 200
    assert r.json().get("session_id") == "client-sid-9"
