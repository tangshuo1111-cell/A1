"""HTTP 契约：校验错误体、限速错误结构、快速 chat stub（第四轮 B-026）。"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from api.main import _rate_limit_exceeded_handler, app
from config.settings import settings


def test_chat_agno_validation_rejects_empty_message(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "api_bearer_token", None)
    with TestClient(app) as client:
        r = client.post("/chat/agno", json={"message": ""})
        assert r.status_code == 422


def test_chat_agno_validation_requires_message_field(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "api_bearer_token", None)
    with TestClient(app) as client:
        r = client.post("/chat/agno", json={"session_id": "x"})
        assert r.status_code == 422


def test_chat_agno_optional_fields_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "api_bearer_token", None)
    monkeypatch.setenv("LIGHT_MAQA_FAKE_LLM", os.environ.get("LIGHT_MAQA_FAKE_LLM", "1"))

    stub = {
        "ok": True,
        "answer": "stub",
        "session_id": None,
        "request_id": None,
        "task_id": None,
        "answer_type": "basic_agno",
        "task_status": "succeeded",
        "primary_path": "agno_basic",
        "pipeline_ok": True,
        "extra": {},
    }

    monkeypatch.setattr(
        "services.agno_chat_service.run_agno_chat_turn",
        lambda *_a, **_k: stub,
    )
    with TestClient(app) as client:
        r = client.post("/chat/agno", json={"message": "hello"})
        assert r.status_code == 200
        body = r.json()
        assert body.get("ok") is True
        assert body.get("answer") == "stub"
        assert body.get("pipeline_ok") is True


def test_rate_limit_json_shape_stable() -> None:
    """不依赖 decorator 阈值；只锁「超限」响应契约。"""
    from unittest.mock import MagicMock

    req = MagicMock()
    resp = _rate_limit_exceeded_handler(req, MagicMock())
    assert resp.status_code == 429
    data = resp.body
    import json

    payload = json.loads(data.decode("utf-8"))
    assert payload.get("ok") is False
    assert payload.get("error", {}).get("code") == "RATE_LIMIT"
