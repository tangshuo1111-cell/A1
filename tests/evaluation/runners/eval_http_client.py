from __future__ import annotations

import os
from typing import Any

import requests


class BackendUnavailableError(RuntimeError):
    """Raised when the local backend cannot be reached."""


class CaseTimeoutError(RuntimeError):
    """Raised when a single eval case request times out."""


class ExecutionError(RuntimeError):
    """Raised when a single eval case request fails during execution."""


class EvalHttpClient:
    def __init__(self, *, base_url: str | None = None, timeout_sec: float = 60.0) -> None:
        self.base_url = (base_url or os.getenv("EVAL_BACKEND_URL") or "http://127.0.0.1:8000").rstrip("/")
        self.timeout_sec = timeout_sec

    def health_check(self) -> dict[str, Any]:
        try:
            response = requests.get(f"{self.base_url}/health", timeout=self.timeout_sec)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            raise BackendUnavailableError(f"backend_unavailable: {self.base_url}/health ({exc})") from exc

    def post_chat_agno(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = requests.post(f"{self.base_url}/chat/agno", json=payload, timeout=self.timeout_sec)
            response.raise_for_status()
            return response.json()
        except requests.Timeout as exc:
            raise CaseTimeoutError(f"case_timeout: {self.base_url}/chat/agno ({exc})") from exc
        except requests.RequestException as exc:
            raise ExecutionError(f"execution_error: {self.base_url}/chat/agno ({exc})") from exc
