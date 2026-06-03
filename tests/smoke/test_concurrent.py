"""Smoke：POST /chat/agno 并发（第二轮 B-010，httpx.AsyncClient + ASGI）。

验证：并行请求均为 200、总时长有界，且响应头 ``X-Request-ID`` 与请求一致（``to_thread`` + contextvars）。
"""

from __future__ import annotations

import asyncio
import sys

import httpx
import pytest
from httpx import ASGITransport
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


@pytest.mark.asyncio
async def test_three_concurrent_post_chat_agno_ok_and_echoes_request_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("services.agno_chat_service.run_agno_chat_turn", _fake_turn)

    transport = ASGITransport(app=app)
    tout = httpx.Timeout(90.0, connect=15.0)

    async def fire(i: int, client: httpx.AsyncClient) -> None:
        rid = f"conc-async-{i}"
        r = await client.post(
            "/chat/agno",
            json={"message": f"ping-{i}", "session_id": f"s-async-{i}"},
            headers={"X-Request-ID": rid},
        )
        assert r.status_code == 200, r.text
        assert r.json().get("ok") is True
        echoed = r.headers.get("x-request-id")
        assert echoed == rid, (echoed, rid)

    async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=tout) as client:
        await asyncio.wait_for(
            asyncio.gather(*(fire(i, client) for i in range(3))),
            timeout=80.0,
        )
