"""Structured JSON 日志。

通过 `setup_structured_logging()` 在 lifespan 中替换默认 handler。
输出格式由环境变量 LOG_FORMAT 控制：json | text（默认 text）。
敏感字段经 ``core.log_redaction`` 脱敏（Round 12）。
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from core.log_redaction import redact_log_message, redact_mapping
from core.request_context import get_request_id, get_session_id


class RedactingFormatter(logging.Formatter):
    """Apply SAFE.log_redact_fields to text log lines."""

    def format(self, record: logging.LogRecord) -> str:
        original = record.msg
        if isinstance(original, str):
            record.msg = redact_log_message(original)
        try:
            return super().format(record)
        finally:
            record.msg = original


class JSONFormatter(RedactingFormatter):
    """每条日志输出一行 JSON，自动注入 request_id/session_id 并脱敏结构化字段。"""

    _EXTRA_FIELDS = (
        "task_id",
        "agent",
        "tool",
        "status",
        "cost_ms",
        "error_code",
        "lane",
        "router_lane",
        "mode",
        "executor_profile",
        "primary_path",
        "pending_kind",
        "task_status",
        "elapsed_ms",
        "timing_total_ms",
        "quality_gate_passed",
    )

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "ts": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "msg": redact_log_message(record.getMessage()),
        }
        rid = get_request_id()
        if rid:
            entry["request_id"] = rid
        sid = get_session_id()
        if sid:
            entry["session_id"] = sid
        if record.exc_info and record.exc_info[1]:
            entry["error"] = redact_log_message(str(record.exc_info[1]))
        for key in self._EXTRA_FIELDS:
            val = getattr(record, key, None)
            if val is not None:
                entry[key] = val
        return json.dumps(redact_mapping(entry), ensure_ascii=False, default=str)


def setup_structured_logging(level: int = logging.INFO) -> None:
    """配置根 logger 的输出格式。

    LOG_FORMAT=json 时用 JSONFormatter；否则保持文本格式（均脱敏）。
    """
    log_format = os.getenv("LOG_FORMAT", "text").lower()
    root = logging.getLogger()

    root.handlers.clear()
    handler = logging.StreamHandler()
    handler.setLevel(level)

    if log_format == "json":
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(RedactingFormatter(
            "%(levelname)s [%(name)s] %(message)s"
        ))

    root.addHandler(handler)
    root.setLevel(level)
    logging.getLogger("light_maqa").setLevel(level)
