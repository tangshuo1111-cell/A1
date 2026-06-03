"""Manual runtime probe for a real Bilibili video chat request.

This script is intentionally placed under tests/manual so it won't be part of
the default CI pytest collection. It is meant for local timing checks against
the real backend route and real provider/tool chain.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from api.main import app  # noqa: E402

VIDEO_URL = "https://www.bilibili.com/video/BV1Q1o5BTEEG/?spm_id_from=333.1007.tianma.5-2-16.click"


def run_probe() -> dict:
    with TestClient(app) as client:
        t0 = time.perf_counter()
        resp = client.post(
            "/chat/agno",
            json={
                "message": f"这个视频讲了什么？请概括核心内容：{VIDEO_URL}",
                "session_id": "manual-bilibili-runtime-probe",
                "use_knowledge": False,
                "confirm_long_web_video_asr": True,
            },
        )
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
    body = resp.json()
    return {
        "http_status": resp.status_code,
        "elapsed_ms": elapsed_ms,
        "task_status": body.get("task_status"),
        "primary_path": body.get("primary_path"),
        "answer": body.get("answer"),
        "extra": body.get("extra", {}),
    }


if __name__ == "__main__":
    print(json.dumps(run_probe(), ensure_ascii=False, indent=2))
