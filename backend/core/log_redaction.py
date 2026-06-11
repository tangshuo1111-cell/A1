"""Log redaction helpers — driven by ``config.safe_rule.SAFE`` (Round 12)."""

from __future__ import annotations

import re
from typing import Any

from config.safe_rule import SAFE

_REDACTED = "***"

# key=value / key: value patterns in free-form log text
_KV_PATTERN = re.compile(
    r"(?i)\b(" + "|".join(re.escape(f) for f in SAFE.log_redact_fields) + r"|secret[_a-z0-9]*"
    r")\s*[:=]\s*(\S+(?:\s+\S+)*)"
)

# Bearer / JWT-like fragments left after partial KV redaction
_BEARER_PATTERN = re.compile(r"(?i)\bBearer\s+\S+")
_JWT_PATTERN = re.compile(r"\b[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")


def _is_sensitive_field(name: str) -> bool:
    lower = name.lower().replace("-", "_")
    for field in SAFE.log_redact_fields:
        token = field.lower().replace("-", "_")
        if lower == token or lower.endswith(f"_{token}") or token in lower:
            return True
    if lower.startswith("secret"):
        return True
    return False


def redact_log_message(message: str) -> str:
    """Redact sensitive key/value fragments inside a log line."""
    if not message:
        return message

    def _repl(match: re.Match[str]) -> str:
        key = match.group(1)
        sep = "=" if "=" in match.group(0) else ":"
        return f"{key}{sep}{_REDACTED}"

    masked = _KV_PATTERN.sub(_repl, message)
    masked = _BEARER_PATTERN.sub(f"Bearer {_REDACTED}", masked)
    masked = _JWT_PATTERN.sub(_REDACTED, masked)
    return masked


def redact_value(name: str, value: Any) -> Any:
    if _is_sensitive_field(name):
        return _REDACTED
    if isinstance(value, dict):
        return redact_mapping(value)
    if isinstance(value, list):
        return [redact_value(name, item) for item in value]
    if isinstance(value, str) and _is_sensitive_field(name):
        return _REDACTED
    return value


def redact_mapping(data: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in data.items():
        if _is_sensitive_field(key):
            out[key] = _REDACTED
        elif isinstance(value, dict):
            out[key] = redact_mapping(value)
        elif isinstance(value, list):
            out[key] = [
                redact_mapping(item) if isinstance(item, dict) else redact_value(key, item)
                for item in value
            ]
        else:
            out[key] = value
    return out
