"""Round 8 — unified API schemas and AppError responses."""

from __future__ import annotations

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
API_ROUTES = PROJECT_ROOT / "backend" / "api" / "routes"


def test_schemas_http_exports_round8_models() -> None:
    from api.schemas_http import (
        ApiErrorDetail,
        ErrorResponse,
        TaskStatusResponse,
        VideoCookiesStatusResponse,
        WebVideoMetadataResponse,
    )

    assert ErrorResponse(ok=False, error=ApiErrorDetail(code="X", message="m")).ok is False
    assert TaskStatusResponse.model_fields["ok"].default is True
    assert WebVideoMetadataResponse.model_fields["ok"].default is True
    assert VideoCookiesStatusResponse.model_fields["ok"].default is True


def test_workflow_elapsed_ms_description_not_langgraph() -> None:
    text = (PROJECT_ROOT / "backend" / "api" / "schemas_http.py").read_text(encoding="utf-8")
    assert "LangGraph" not in text
    assert "chat turn" in text


def test_public_routes_declare_response_models() -> None:
    targets = {
        "chat_agno.py": "ChatResponse",
        "tasks.py": "TaskStatusResponse",
        "sessions.py": "SessionSummaryResponse",
        "video_cookies.py": "VideoCookiesStatusResponse",
        "web_video.py": "WebVideoMetadataResponse",
    }
    for filename, model_name in targets.items():
        text = (API_ROUTES / filename).read_text(encoding="utf-8")
        assert "response_model=" in text, filename
        assert model_name in text, filename


def test_target_route_handlers_not_dict_annotated() -> None:
    for filename in ("tasks.py", "sessions.py", "web_video.py"):
        text = (API_ROUTES / filename).read_text(encoding="utf-8")
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not node.decorator_list or node.returns is None:
                continue
            ret = ast.unparse(node.returns)
            assert ret != "dict", f"{filename}:{node.name} still annotated -> dict"
    cookies = (API_ROUTES / "video_cookies.py").read_text(encoding="utf-8")
    for handler in ("video_cookies_status", "upload_video_cookies", "delete_video_cookies"):
        chunk = cookies.split(f"def {handler}")[1].split("\ndef ")[0]
        assert "-> dict" not in chunk, handler


def test_tasks_and_sessions_use_app_error_helpers() -> None:
    for filename in ("tasks.py", "sessions.py", "chat_agno.py"):
        text = (API_ROUTES / filename).read_text(encoding="utf-8")
        assert "HTTPException" not in text, filename
        assert "api_errors" in text or "AppError" in text, filename


def test_app_error_supports_custom_http_status() -> None:
    from core.errors import AppError, ErrorCategory, http_status_for_error

    exc = AppError(
        code="FILE_TOO_LARGE",
        message="too big",
        category=ErrorCategory.VALIDATION,
        http_status=413,
    )
    assert http_status_for_error(exc) == 413


def test_app_error_body_matches_error_response() -> None:
    from api.schemas_http import ErrorResponse
    from core.errors import AppError, ErrorCategory

    body = AppError(
        code="TASK_NOT_FOUND",
        message="missing",
        category=ErrorCategory.NOT_FOUND,
    ).to_api_body(request_id="rid-1")
    parsed = ErrorResponse.model_validate(body)
    assert parsed.error.code == "TASK_NOT_FOUND"
    assert parsed.request_id == "rid-1"


def test_web_video_route_no_ok_false_success_path() -> None:
    text = (API_ROUTES / "web_video.py").read_text(encoding="utf-8")
    assert '"ok": False' not in text
    assert "'ok': False" not in text
