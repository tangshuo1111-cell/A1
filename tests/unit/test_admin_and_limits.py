"""管理边界：ADMIN_API_KEY 与 internal 路由。"""

from fastapi.testclient import TestClient

from api.main import app
from config.settings import settings


def test_internal_metrics_requires_key_when_configured(monkeypatch) -> None:
    monkeypatch.setattr(settings, "admin_api_key", "secret-admin")
    with TestClient(app) as client:
        r = client.get("/internal/metrics")
        assert r.status_code == 403
        r2 = client.get("/internal/metrics", headers={"X-Admin-Key": "secret-admin"})
        assert r2.status_code == 200
        assert r2.json().get("ok") is True
        assert "counters" in r2.json()


def test_ingest_blocked_without_admin_key(monkeypatch) -> None:
    monkeypatch.setattr(settings, "admin_api_key", "k")
    with TestClient(app) as client:
        r = client.post("/ingest/samples")
        assert r.status_code == 403
