"""Status taxonomy and aggregation for real_external_smoke (evaluation report layer only)."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

REAL_EXTERNAL_STATUSES = frozenset({
    "not_configured",
    "dependency_missing",
    "backend_unavailable",
    "external_timeout",
    "external_unavailable",
    "skipped",
    "configured_and_passed",
    "configured_and_failed",
})

PRODUCT_FAILURE_REASONS = frozenset({
    "fake_success_detected",
    "kb_lifecycle_broken",
    "routing_honesty_failure",
})

NON_PRODUCT_FAILURE_REASONS = frozenset({
    "missing_llm_key",
    "missing_asr_key",
    "missing_ocr_key",
    "missing_video_url",
    "fake_llm_enabled",
    "credential_invalid",
    "external_config_error",
    "provider_timeout",
    "network_unreachable",
    "ffmpeg_not_found",
    "playwright_not_found",
    "postgres_not_configured",
    "postgres_unreachable",
    "backend_unreachable",
    "dependency_not_installed",
    "tool_not_found",
    "ocr_no_text",
    "ocr_provider_error",
})

DEPENDENCY_MISSING_ERROR_CODES = frozenset({
    "tool_not_found",
    "dependency_not_installed",
    "dependency_missing",
    "parser_dependency_missing",
    "ffmpeg_not_found",
    "playwright_not_found",
    "ffprobe_not_found",
    "ytdlp_not_found",
    "asr_dependency_missing",
    "ocr_dependency_missing",
})


def is_dependency_missing_error(error_code: str) -> bool:
    code = str(error_code or "").strip().lower()
    if not code:
        return False
    if code in DEPENDENCY_MISSING_ERROR_CODES:
        return True
    if code.startswith("missing:"):
        return False
    return "dependency" in code


def dependency_missing_reason_from_errors(errors: list[str]) -> str | None:
    for raw in errors:
        code = str(raw or "").strip()
        if not is_dependency_missing_error(code):
            continue
        lowered = code.lower()
        if lowered == "tool_not_found":
            return "tool_not_found"
        if lowered == "dependency_not_installed":
            return "dependency_not_installed"
        if lowered in DEPENDENCY_MISSING_ERROR_CODES:
            return lowered
        return "dependency_not_installed"
    return None


OCR_NO_TEXT_ERROR_CODES = frozenset({
    "ocr_empty_result",
})


def is_credential_error(error_code: str) -> bool:
    lowered = str(error_code or "").strip().lower()
    if not lowered:
        return False
    markers = (
        "unauthorized",
        "invalidapikey",
        "invalid_api_key",
        "authentication",
        "accessdenied",
        "access_denied",
        "signature",
        "token expired",
        "invalidtoken",
        "invalid_token",
        "authfail",
        "forbidden",
        "incorrect api key",
        "api key invalid",
    )
    return any(marker in lowered for marker in markers)


def is_ocr_no_text_error(error_code: str) -> bool:
    code = str(error_code or "").strip()
    lowered = code.lower()
    if code in OCR_NO_TEXT_ERROR_CODES:
        return True
    return "imagenotext" in lowered or "no_text" in lowered or "empty_result" in lowered


def ocr_failure_reason_from_error_code(error_code: str) -> str:
    err = str(error_code or "").strip()
    if is_ocr_no_text_error(err):
        return "ocr_no_text"
    if "timeout" in err.lower():
        return "provider_timeout"
    if is_credential_error(err):
        return "credential_invalid"
    return "ocr_provider_error"


def ocr_failure_status_from_error_code(error_code: str) -> tuple[str, str]:
    reason = ocr_failure_reason_from_error_code(error_code)
    if reason == "provider_timeout":
        return "external_timeout", reason
    return "configured_and_failed", reason


SANITIZE_PATTERNS = (
    (re.compile(r"sk-[A-Za-z0-9]{8,}", re.I), "<REDACTED_API_KEY>"),
    (re.compile(r"Bearer\s+\S+", re.I), "Bearer <REDACTED_TOKEN>"),
    (re.compile(r"(?i)(api[_-]?key|secret|token|cookie)\s*[:=]\s*\S+"), r"\1=<REDACTED>"),
    (re.compile(r"[A-Za-z]:\\Users\\[^\\]+"), r"<USER_HOME>"),
    (re.compile(r"/Users/[^/]+"), r"<USER_HOME>"),
)


def candidate_project_env_files(repo_root: Path) -> list[Path]:
    """Mirror backend/config/_helpers._candidate_env_files without importing settings."""
    candidates: list[Path] = [
        repo_root / ".env",
        repo_root / "backend" / "config" / "env.txt",
    ]
    for parent in list(repo_root.parents)[:3]:
        candidates.append(parent / ".env")
    unique: list[Path] = []
    seen: set[Path] = set()
    for path in candidates:
        resolved = path.resolve()
        if resolved not in seen:
            unique.append(path)
            seen.add(resolved)
    return unique


def load_project_env_files(repo_root: Path, *, override: bool = False) -> list[str]:
    """Load project env files into os.environ; returns relative paths loaded (no values)."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return []

    loaded: list[str] = []
    for path in candidate_project_env_files(repo_root):
        if not path.exists():
            continue
        load_dotenv(path, override=override)
        try:
            loaded.append(path.relative_to(repo_root).as_posix())
        except ValueError:
            loaded.append(str(path))
    return loaded


def mask_secret_value(value: str) -> str:
    val = str(value or "").strip()
    if not val:
        return ""
    if len(val) < 4:
        return "<set>"
    return f"{val[:2]}****{val[-2:]}"


def summarize_env_secret(name: str) -> dict[str, Any]:
    raw = os.environ.get(name, "")
    val = raw.strip() if isinstance(raw, str) else ""
    if not val:
        return {"present": False}
    return {
        "present": True,
        "length": len(val),
        "masked": mask_secret_value(val),
    }


def build_environment_summary(*, env_files_loaded: list[str]) -> dict[str, Any]:
    return {
        "env_files_loaded": list(env_files_loaded),
        "LIGHT_MAQA_FAKE_LLM": "1" if os.environ.get("LIGHT_MAQA_FAKE_LLM", "").strip().lower() in {"1", "true", "yes", "on"} else "0",
        "DATABASE_URL_set": bool(os.environ.get("DATABASE_URL", "").strip()),
        "REAL_VIDEO_TEST_URL_set": bool(os.environ.get("REAL_VIDEO_TEST_URL", "").strip()),
        "REAL_EXTERNAL_RUN_REGRESSION": os.environ.get("REAL_EXTERNAL_RUN_REGRESSION", "0"),
        "LLM_API_KEY": summarize_env_secret("LLM_API_KEY"),
        "OPENAI_API_KEY": summarize_env_secret("OPENAI_API_KEY"),
    }


def make_entry(
    *,
    case_id: str,
    status: str,
    configured: bool,
    product_failure: bool = False,
    reason: str = "",
    detail: dict[str, Any] | None = None,
    duration_ms: int = 0,
) -> dict[str, Any]:
    if status not in REAL_EXTERNAL_STATUSES:
        raise ValueError(f"invalid real_external status: {status}")
    return {
        "case_id": case_id,
        "status": status,
        "configured": configured,
        "product_failure": product_failure,
        "reason": reason,
        "detail": detail or {},
        "duration_ms": duration_ms,
    }


def resolve_product_failure(*, status: str, reason: str) -> bool:
    if status != "configured_and_failed":
        return False
    if reason in PRODUCT_FAILURE_REASONS:
        return True
    if reason in NON_PRODUCT_FAILURE_REASONS:
        return False
    return False


def aggregate_capability_summary(capability_cases: list[dict[str, Any]]) -> dict[str, int]:
    summary = {
        "configured_cases_count": 0,
        "passed_configured_cases_count": 0,
        "not_configured_cases_count": 0,
        "dependency_missing_cases_count": 0,
        "external_timeout_cases_count": 0,
        "skipped_cases_count": 0,
        "failed_cases_count": 0,
        "product_failure_cases_count": 0,
    }
    for case in capability_cases:
        status = str(case.get("status") or "")
        configured = bool(case.get("configured"))
        product_failure = bool(case.get("product_failure"))
        if configured:
            summary["configured_cases_count"] += 1
        if status == "configured_and_passed":
            summary["passed_configured_cases_count"] += 1
        if status == "not_configured":
            summary["not_configured_cases_count"] += 1
        if status == "dependency_missing":
            summary["dependency_missing_cases_count"] += 1
        if status == "external_timeout":
            summary["external_timeout_cases_count"] += 1
        if status == "skipped":
            summary["skipped_cases_count"] += 1
        if product_failure:
            summary["failed_cases_count"] += 1
            summary["product_failure_cases_count"] += 1
    return summary


def compute_final_verdict(
    *,
    capability_cases: list[dict[str, Any]],
    backend_available: bool,
) -> str:
    summary = aggregate_capability_summary(capability_cases)
    if summary["product_failure_cases_count"] > 0:
        return "product_failure_detected"
    if summary["passed_configured_cases_count"] > 0:
        if summary["external_timeout_cases_count"] > 0:
            return "environment_partial"
        return "environment_ready"
    if not backend_available and summary["configured_cases_count"] == 0:
        return "environment_not_ready"
    if summary["not_configured_cases_count"] == len(capability_cases):
        return "environment_not_ready"
    return "environment_partial"


def compute_exit_code(
    *,
    runner_error: bool = False,
    backend_unavailable: bool = False,
    configured_cases_count: int = 0,
    product_failure_cases_count: int = 0,
    optional_regression_failed_unknown: bool = False,
) -> int:
    if runner_error:
        return 1
    if backend_unavailable and configured_cases_count == 0:
        return 2
    if product_failure_cases_count > 0:
        return 3
    if optional_regression_failed_unknown:
        return 4
    return 0


def sanitize_text(text: str) -> str:
    out = str(text or "")
    for pattern, repl in SANITIZE_PATTERNS:
        out = pattern.sub(repl, out)
    return out


def build_sanitized_summary(report: dict[str, Any]) -> str:
    lines = [
        f"suite={report.get('suite_name')}",
        f"final_verdict={report.get('final_verdict')}",
        f"backend={report.get('backend_base_url')}",
    ]
    summary = report.get("summary") or {}
    lines.append(
        "counts: "
        f"passed_configured={summary.get('passed_configured_cases_count', 0)} "
        f"not_configured={summary.get('not_configured_cases_count', 0)} "
        f"product_failure={summary.get('product_failure_cases_count', 0)}"
    )
    for block_name in ("dependency_preflight", "capability_cases"):
        for item in report.get(block_name) or []:
            lines.append(
                f"{block_name}:{item.get('case_id')} "
                f"status={item.get('status')} configured={item.get('configured')} "
                f"product_failure={item.get('product_failure')} reason={item.get('reason')}"
            )
    return sanitize_text("\n".join(lines))


def build_recommendations(report: dict[str, Any]) -> list[str]:
    recs: list[str] = []
    summary = report.get("summary") or {}
    env = report.get("environment_summary") or {}
    if env.get("LIGHT_MAQA_FAKE_LLM") == "1":
        recs.append("Set LIGHT_MAQA_FAKE_LLM=0 and provide LLM_API_KEY for real LLM smoke.")
    if summary.get("not_configured_cases_count", 0) > 0:
        recs.append("Configure missing provider keys or optional REAL_VIDEO_TEST_URL before staging smoke.")
    if summary.get("dependency_missing_cases_count", 0) > 0:
        recs.append("Install missing dependencies (Playwright Chromium, ffmpeg, PostgreSQL).")
    if summary.get("product_failure_cases_count", 0) > 0:
        recs.append("Investigate product honesty failures; consider opening a known issue after manual review.")
    if not recs:
        recs.append("Environment smoke completed; review configured_and_passed cases for staging evidence.")
    return recs
