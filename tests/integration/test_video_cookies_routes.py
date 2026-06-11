"""Round 13 — video cookies admin routes: status, upload validation, delete."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import app
from config.settings import settings

_VALID_COOKIES = (
    "# Netscape HTTP Cookie File\n"
    ".bilibili.com\tTRUE\t/\tFALSE\t1735689600\tSESSDATA\ttest-session\n"
)


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(settings, "api_bearer_token", None)
    monkeypatch.setattr(settings, "admin_api_key", None)
    with TestClient(app) as test_client:
        yield test_client


def test_video_cookies_status_shape(client: TestClient) -> None:
    r = client.get("/config/video_cookies/status")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert "whitelist_domains" in body
    assert "upload_max_bytes" in body
    assert body["upload_max_bytes"] == 1_048_576


def test_upload_empty_file_rejected(client: TestClient) -> None:
    r = client.post(
        "/config/video_cookies/upload",
        files={"file": ("cookies.txt", b"", "text/plain")},
    )
    assert r.status_code == 400
    body = r.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "EMPTY_FILE"


def test_upload_invalid_format_rejected(client: TestClient) -> None:
    r = client.post(
        "/config/video_cookies/upload",
        files={"file": ("cookies.txt", b"not a cookie file\n", "text/plain")},
    )
    assert r.status_code == 400
    body = r.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "NOT_COOKIES_TXT"


def test_upload_valid_cookies_ok(client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    r = client.post(
        "/config/video_cookies/upload",
        files={"file": ("cookies.txt", _VALID_COOKIES.encode("utf-8"), "text/plain")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["hot_reloaded"] is True
    assert "bilibili.com" in body["matched_whitelist_domains"]


def test_delete_cookies_idempotent(client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    upload = client.post(
        "/config/video_cookies/upload",
        files={"file": ("cookies.txt", _VALID_COOKIES.encode("utf-8"), "text/plain")},
    )
    assert upload.status_code == 200

    r = client.delete("/config/video_cookies")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["removed"] is True

    again = client.delete("/config/video_cookies")
    assert again.status_code == 200
    assert again.json()["ok"] is True


def test_admin_key_required_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "api_bearer_token", None)
    monkeypatch.setattr(settings, "admin_api_key", "test-admin-secret")
    with TestClient(app) as client:
        r = client.get("/config/video_cookies/status")
        assert r.status_code == 403
        body = r.json()
        assert body["ok"] is False
        assert body["error"]["code"] == "ADMIN_KEY_REQUIRED"

        ok = client.get(
            "/config/video_cookies/status",
            headers={"X-Admin-Key": "test-admin-secret"},
        )
        assert ok.status_code == 200
        assert ok.json()["ok"] is True
