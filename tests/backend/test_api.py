"""
HTTP API 烟测（V9 R3）：

V9 R3 物理删除旧 LangGraph 链后，唯一公开 chat 主路由是 POST /chat/agno，
旧 POST /chat、/chat/async 已不再存在；/tasks/{id} 已恢复为 pending 查询契约。

本测试仅做最小连通性断言：
- GET /health
- POST /chat/agno（默认主路由）
"""
from fastapi.testclient import TestClient

from api.main import app


def test_health():
    with TestClient(app) as client:
        r = client.get("/health")
        assert r.status_code == 200
        body = r.json()
        assert body.get("status") in ("ok", "degraded")
        assert "checks" in body


def test_chat_agno_default_route():
    """V9 R3：默认主路由 POST /chat/agno 必须 200，且返回业务字段齐全。"""
    with TestClient(app) as client:
        r = client.post("/chat/agno", json={"message": "你好", "session_id": "v9r3-smoke"})
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data.get("primary_path") == "canned"
        assert data.get("session_id") == "v9r3-smoke"
        extra = data.get("extra") or {}
        assert extra.get("lane") == "general"
        assert extra.get("fast_lane_name") == "general"
        assert extra.get("fast_path") == "canned"
        assert "capability.general.canned_answer" in (extra.get("capabilities_called") or [])


def test_legacy_chat_routes_removed():
    """V9 R3：旧 LangGraph 入口 POST /chat、/chat/async 必须返回 404。"""
    with TestClient(app) as client:
        r = client.post("/chat", json={"message": "你好"})
        assert r.status_code == 404, "POST /chat 必须已物理移除"
        r2 = client.post("/chat/async", json={"message": "你好"})
        assert r2.status_code == 404, "POST /chat/async 必须已物理移除"


def test_video_metadata_route_times_out_fast(monkeypatch):
    import time

    monkeypatch.setattr("api.routes.web_video.is_supported_video_url", lambda url: True)
    monkeypatch.setattr("api.routes.web_video.settings.v16_video_probe_timeout_sec", 0.01)

    def _slow_probe(url: str) -> dict:
        time.sleep(0.2)
        return {"ok": True, "title": "late"}

    monkeypatch.setattr("api.routes.web_video.probe_web_video_metadata", _slow_probe)

    with TestClient(app) as client:
        r = client.post("/video/metadata", json={"url": "https://example.com/video"})
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is False
        assert body["error"] == "video_probe_timeout"
        assert isinstance(body.get("latency_ms"), int)
