from __future__ import annotations

import functools
import http.server
import socketserver
import threading
from pathlib import Path


def _serve(tmp_path: Path):
    (tmp_path / "a.html").write_text(
        "<html><head><title>A View</title></head><body><article>"
        "<h1>A View</h1><p>A focuses on access, productivity, and broader reach for AI adoption. "
        "It also mentions privacy risk and uneven quality for difficult decisions.</p></article></body></html>",
        encoding="utf-8",
    )
    (tmp_path / "b.html").write_text(
        "<html><head><title>B View</title></head><body><article>"
        "<h1>B View</h1><p>B focuses on governance, caution, and institutional control. "
        "It highlights slower experimentation as a tradeoff.</p></article></body></html>",
        encoding="utf-8",
    )
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(tmp_path))
    server = socketserver.TCPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def _question(base: str, second: str = "missing.html") -> str:
    return (
        "请对比这两个网页分别表达了什么，它们的角度、优点和局限有什么不同：\n"
        f"{base}/a.html\n{base}/{second}"
    )


def test_default_chain_runs_feedback_gate_and_round_delta(tmp_path, monkeypatch):
    from config import feature_flags
    from services.agno_chat_service import run_agno_chat_turn

    monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_COMPLEX_REFINE_V2", False)

    server, base = _serve(tmp_path)
    try:
        out = run_agno_chat_turn(_question(base), session_id="v17r2-default")
    finally:
        server.shutdown()
    extra = out["extra"]
    assert extra["v17_job_type"] == "multi_source_compare"
    assert extra["tool_plan"]["steps"]
    assert extra["fallback_steps"]
    assert extra["source_tasks"]
    assert extra["source_briefs"]
    assert extra["comparison_matrix"]["comparison_id"]
    assert extra["critic_check"]["critic_check_id"]
    assert extra["feedback_request"]["feedback_request_id"]
    assert extra["feedback_gate_result"]["allowed"] is True
    assert extra["round_delta"]["feedback_result"]["allowed"] is True
    assert extra["used_rounds"] == [0, 1]
    assert extra["final_answer"]
