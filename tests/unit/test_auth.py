"""Bearer 认证（第一轮 B-005）。"""

from __future__ import annotations

import os

from fastapi.testclient import TestClient

from api.main import app
from config.settings import settings


def test_public_paths_no_bearer_when_auth_configured(monkeypatch) -> None:
    monkeypatch.setattr(settings, "api_bearer_token", "srv-secret")
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/openapi.json").status_code == 200
        assert client.get("/docs").status_code == 200
        assert client.get("/redoc").status_code == 200


def test_chat_agno_requires_bearer_when_auth_configured(monkeypatch) -> None:
    monkeypatch.setattr(settings, "api_bearer_token", "srv-secret")
    with TestClient(app) as client:
        r = client.post("/chat/agno", json={"message": "hello"})
        assert r.status_code == 401
        data = r.json()
        assert data.get("ok") is False
        assert data.get("error", {}).get("code") == "UNAUTHORIZED"


def test_chat_agno_wrong_bearer_returns_401(monkeypatch) -> None:
    monkeypatch.setattr(settings, "api_bearer_token", "srv-secret")
    with TestClient(app) as client:
        r = client.post(
            "/chat/agno",
            json={"message": "hello"},
            headers={"Authorization": "Bearer wrong"},
        )
        assert r.status_code == 401
        assert r.json().get("error", {}).get("code") == "UNAUTHORIZED"


def test_no_auth_setting_allows_without_bearer(monkeypatch) -> None:
    monkeypatch.setattr(settings, "api_bearer_token", None)
    with TestClient(app) as client:
        r = client.post("/chat/agno", json={"message": "ping"})
        assert r.status_code == 200
        assert r.json().get("ok") is True


def test_valid_bearer_allows_chat(monkeypatch) -> None:
    monkeypatch.setattr(settings, "api_bearer_token", "srv-secret")
    monkeypatch.setenv("LIGHT_MAQA_FAKE_LLM", os.environ.get("LIGHT_MAQA_FAKE_LLM", "1"))
    with TestClient(app) as client:
        r = client.post(
            "/chat/agno",
            json={"message": "ping"},
            headers={"Authorization": "Bearer srv-secret"},
        )
        assert r.status_code == 200
        assert r.json().get("ok") is True
