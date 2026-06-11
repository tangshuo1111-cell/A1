"""Internal metrics snapshot contract."""

from __future__ import annotations

from fastapi.testclient import TestClient

from api.main import app
from observability import (
    metrics_prometheus_text,
    metrics_record_chat_async_submitted,
    metrics_record_chat_sync,
    metrics_record_graph_node,
    metrics_record_request,
    metrics_record_retrieval_mode,
    metrics_record_task_terminal,
    metrics_record_tool_call,
    reset_metrics_for_tests,
)


def test_internal_metrics_snapshot_reports_chat_and_tool_counters() -> None:
    reset_metrics_for_tests()
    metrics_record_chat_sync(True)
    metrics_record_chat_sync(False)
    metrics_record_chat_async_submitted()
    metrics_record_task_terminal("succeeded")
    metrics_record_tool_call("search", True)
    metrics_record_retrieval_mode("hybrid")
    metrics_record_graph_node("answer")
    metrics_record_request("/chat/agno", 200, 42.8)

    with TestClient(app) as client:
        payload = client.get("/internal/metrics").json()
        prom = client.get("/internal/metrics/prometheus")

    assert prom.status_code == 200
    assert "light_maqa_counter_chat_sync_total" in prom.text
    assert "light_maqa_http_latency_avg_ms" in prom.text
    assert "light_maqa_retrieval_mode_total" in prom.text

    counters = payload["counters"]
    assert payload["ok"] is True
    assert counters["chat_sync_total"] == 2
    assert counters["chat_sync_ok"] == 1
    assert counters["chat_sync_fail"] == 1
    assert counters["chat_async_submitted_total"] == 1
    assert counters["task_terminal_succeeded"] == 1
    assert counters["tool_calls_total"] == 1
    assert counters["tool_search_ok"] == 1
    assert counters["http_requests_total"] >= 1
    assert counters["http_status_200"] >= 1
    assert payload["retrieval_modes"]["hybrid"] == 1
    assert payload["graph_nodes"]["answer"] == 1
    assert payload["http_latency_avg_ms"] >= 0

    reset_metrics_for_tests()
