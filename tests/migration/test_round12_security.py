"""Round 12 — log redaction and proxy header hardening."""

from __future__ import annotations

import json
import logging
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_structured_logger_uses_redaction() -> None:
    text = (PROJECT_ROOT / "backend" / "core" / "structured_logger.py").read_text(encoding="utf-8")
    assert "log_redaction" in text
    assert "redact_log_message" in text


def test_safe_rule_defines_redact_fields() -> None:
    from config.safe_rule import SAFE

    fields = {f.lower() for f in SAFE.log_redact_fields}
    assert "authorization" in fields
    assert "cookie" in fields
    assert "token" in fields
    assert "api_key" in fields


def test_redact_log_message_masks_kv_pairs() -> None:
    from core.log_redaction import redact_log_message

    raw = "upload failed api_key=sk-live-abcdef authorization: Bearer abc.def.ghi"
    masked = redact_log_message(raw)
    assert "sk-live-abcdef" not in masked
    assert "abc.def.ghi" not in masked
    assert "***" in masked


def test_json_formatter_redacts_message_field() -> None:
    from core.structured_logger import JSONFormatter

    record = logging.LogRecord(
        name="light_maqa",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="auth failure token=abc123secret",
        args=(),
        exc_info=None,
    )
    payload = json.loads(JSONFormatter().format(record))
    assert "abc123secret" not in payload["msg"]
    assert "***" in payload["msg"]


def test_json_formatter_includes_turn_observability_fields() -> None:
    from core.structured_logger import JSONFormatter

    record = logging.LogRecord(
        name="light_maqa",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="turn finished",
        args=(),
        exc_info=None,
    )
    record.lane = "kb"
    record.mode = "fast"
    record.primary_path = "kb_fast"
    record.executor_profile = "fast"
    record.pending_kind = "none"
    record.task_status = "succeeded"
    record.elapsed_ms = 123
    payload = json.loads(JSONFormatter().format(record))
    assert payload["lane"] == "kb"
    assert payload["mode"] == "fast"
    assert payload["primary_path"] == "kb_fast"
    assert payload["executor_profile"] == "fast"
    assert payload["task_status"] == "succeeded"
    assert payload["elapsed_ms"] == 123


def test_proxy_route_uses_allowlist() -> None:
    route = PROJECT_ROOT / "frontend" / "app" / "api-proxy" / "[...path]" / "route.ts"
    text = route.read_text(encoding="utf-8")
    assert "proxyAllowedHeaders" in text
    assert "copyAllowedProxyRequestHeaders" in text


def test_ci_audit_steps_are_semi_blocking() -> None:
    """pip/npm audit 半阻断：官方 registry + 无 continue-on-error（台账见 security_audit_record.md）。"""
    ci = (PROJECT_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "pip-audit" in ci
    assert "pip_audit -r requirements.lock" in ci
    assert "npm audit" in ci
    assert "registry.npmjs.org" in ci
    assert "continue-on-error: true" not in ci


def test_video_cookies_admin_gated_and_metadata_only_logs() -> None:
    text = (PROJECT_ROOT / "backend" / "api" / "routes" / "video_cookies.py").read_text(
        encoding="utf-8"
    )
    assert "dependencies=[Depends(verify_admin_optional)]" in text
    log_blocks = text.split("logger.info")
    for block in log_blocks[1:]:
        call = block.split(")", 1)[0]
        assert "merged_text" not in call
        assert "merged_bytes" not in call
        assert "content," not in call  # no raw cookie body in log args
        assert "content)" not in call
