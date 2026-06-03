"""结构化 JSON 日志。

通过 `setup_structured_logging()` 在 lifespan 中替换默认 handler。
输出格式由环境变量 LOG_FORMAT 控制：json | text（默认 text）。
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from core.request_context import get_request_id, get_session_id


class JSONFormatter(logging.Formatter):
    """每条日志输出一行 JSON，自动注入 request_id/session_id。"""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "ts": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        rid = get_request_id()
        if rid:
            entry["request_id"] = rid
        sid = get_session_id()
        if sid:
            entry["session_id"] = sid
        if record.exc_info and record.exc_info[1]:
            entry["error"] = str(record.exc_info[1])
        for key in ("task_id", "agent", "tool", "status", "cost_ms", "error_code"):
            val = getattr(record, key, None)
            if val is not None:
                entry[key] = val
        return json.dumps(entry, ensure_ascii=False, default=str)


def setup_structured_logging(level: int = logging.INFO) -> None:
    """配置根 logger 的输出格式。

    LOG_FORMAT=json 时用 JSONFormatter；否则保持文本格式。
    """
    log_format = os.getenv("LOG_FORMAT", "text").lower()
    root = logging.getLogger()

    root.handlers.clear()
    handler = logging.StreamHandler()
    handler.setLevel(level)

    if log_format == "json":
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(logging.Formatter(
            "%(levelname)s [%(name)s] %(message)s"
        ))

    root.addHandler(handler)
    root.setLevel(level)
    logging.getLogger("light_maqa").setLevel(level)
