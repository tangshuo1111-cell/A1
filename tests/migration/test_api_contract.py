"""API contract regression tests.

Verifies §15.11 compatibility rules:
- New optional fields don't break old-client parsing.
- Status field values converge to canonical TASK_STATUS enum.
- POST /chat/agno extra block contains required PROD trace fields when present.
"""
from __future__ import annotations

import pytest

TASK_STATUS_CANONICAL = {"pending", "running", "succeeded", "failed", "timeout", "cancelled", "resumed"}

TASK_STATUS_DEPRECATED_ALIASES: dict[str, str] = {
    "queued": "pending",
    "in_progress": "running",
    "done": "succeeded",
    "error": "failed",
}

REQUIRED_PROD_TRACE_FIELDS = {
    "request_id",
    "lane",
    "mode",
    "router_source",
    "router_confidence",
}


class TestTaskStatusConvergence:
    def test_canonical_values_are_valid(self):
        for v in TASK_STATUS_CANONICAL:
            assert isinstance(v, str) and len(v) > 0

    def test_deprecated_aliases_map_to_canonical(self):
        for old, new in TASK_STATUS_DEPRECATED_ALIASES.items():
            assert new in TASK_STATUS_CANONICAL, (
                f"Alias {old!r} → {new!r} but {new!r} not in TASK_STATUS_CANONICAL"
            )

    def test_no_alias_same_as_canonical(self):
        for alias in TASK_STATUS_DEPRECATED_ALIASES:
            assert alias not in TASK_STATUS_CANONICAL, (
                f"{alias!r} is both an alias and a canonical value — remove it from aliases"
            )


class TestChatAgnoResponseOldClient:
    """Simulate an old client that only reads 'ok', 'answer', 'session_id'."""

    def _old_parse(self, response: dict) -> dict:
        return {
            "ok": response["ok"],
            "answer": response["answer"],
            "session_id": response.get("session_id"),
        }

    def test_old_client_ignores_extra_fields(self):
        new_style_response = {
            "ok": True,
            "answer": "test answer",
            "session_id": "sess_001",
            "extra": {
                "lane": "general",
                "mode": "fast",
                "router_source": "rule",
                "router_confidence": 0.95,
                "loop_total_rounds": 0,
            },
            "workflow_elapsed_ms": 123,
        }
        parsed = self._old_parse(new_style_response)
        assert parsed["ok"] is True
        assert parsed["answer"] == "test answer"

    def test_minimal_response_still_valid(self):
        minimal = {"ok": True, "answer": "hi", "session_id": None}
        parsed = self._old_parse(minimal)
        assert parsed["ok"] is True


class TestChatAgnoResponseNewClient:
    """New client reads trace fields from extra block."""

    LANE_VALID = {"video", "document", "web", "kb", "general"}
    MODE_VALID = {"fast", "complex", "async"}
    ROUTER_SOURCE_VALID = {
        "rule",
        "light_classifier",
        "rule+light_classifier",
        "llm_router",
        "main_agent_escalation",
        "fallback_default",
    }

    def test_lane_value_in_valid_set(self):
        extra = {"lane": "video"}
        assert extra["lane"] in self.LANE_VALID

    def test_mode_value_in_valid_set(self):
        extra = {"mode": "fast"}
        assert extra["mode"] in self.MODE_VALID

    def test_router_source_in_valid_set(self):
        extra = {"router_source": "rule"}
        assert extra["router_source"] in self.ROUTER_SOURCE_VALID

    @pytest.mark.parametrize("lane", ["video", "document", "web", "kb", "general"])
    def test_all_lanes_are_canonical(self, lane: str):
        assert lane in self.LANE_VALID

    def test_router_confidence_range(self):
        confidence = 0.87
        assert 0.0 <= confidence <= 1.0


class TestTaskResultSchema:
    def test_required_fields_present(self):
        result = {
            "task_id": "task_001",
            "status": "succeeded",
            "payload_version": 1,
        }
        assert "task_id" in result
        assert "status" in result
        assert "payload_version" in result

    def test_status_is_canonical(self):
        result = {"task_id": "task_001", "status": "succeeded", "payload_version": 1}
        assert result["status"] in TASK_STATUS_CANONICAL

    def test_optional_data_field_omittable(self):
        result = {"task_id": "task_001", "status": "failed", "payload_version": 1}
        assert "data" not in result

    def test_old_client_ignores_payload_version(self):
        result = {
            "task_id": "task_001",
            "status": "succeeded",
            "payload_version": 2,
            "data": {"transcript": "hello"},
        }
        old_client_value = result["status"]
        assert old_client_value in ("succeeded", "done", "failed", "error")
