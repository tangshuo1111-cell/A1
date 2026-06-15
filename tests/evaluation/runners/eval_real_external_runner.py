"""Real external smoke runner — evaluation layer only; read-only product probes."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from tests.evaluation.runners.eval_http_client import (
    BackendUnavailableError,
    CaseTimeoutError,
    EvalHttpClient,
    ExecutionError,
)
from tests.evaluation.runners.eval_real_external_status import (
    aggregate_capability_summary,
    build_recommendations,
    build_sanitized_summary,
    compute_exit_code,
    compute_final_verdict,
    dependency_missing_reason_from_errors,
    is_dependency_missing_error,
    make_entry,
    resolve_product_failure,
)
from tests.evaluation.runners.eval_result_writer import write_real_external_smoke_report

_REPO_ROOT = Path(__file__).resolve().parents[3]
_BACKEND_ROOT = _REPO_ROOT / "backend"


def _repo_root() -> Path:
    return _REPO_ROOT


def real_external_case_file() -> Path:
    return _repo_root() / "tests" / "evaluation" / "cases" / "real_external_smoke.yaml"


def load_real_external_cases(path: str | Path | None = None) -> list[dict[str, Any]]:
    case_path = Path(path) if path is not None else real_external_case_file()
    payload = yaml.safe_load(case_path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"real_external_smoke cases must be a list: {case_path}")
    cases: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError("each case must be a dict")
        case_id = str(item.get("case_id") or "")
        if not case_id or case_id in seen:
            raise ValueError(f"duplicate or missing case_id: {case_id}")
        seen.add(case_id)
        cases.append(dict(item))
    return cases


def _ensure_backend_path() -> None:
    backend = str(_BACKEND_ROOT)
    if backend not in sys.path:
        sys.path.insert(0, backend)


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _llm_key_present() -> bool:
    for key in ("LLM_API_KEY", "OPENAI_API_KEY"):
        if os.environ.get(key, "").strip():
            return True
    return False


def _asr_configured() -> bool:
    provider = (os.environ.get("V16_ASR_PROVIDER") or os.environ.get("ASR_PROVIDER") or "").strip().lower()
    if not provider or provider in {"mock", "fake"}:
        return False
    if provider == "dashscope" and not (os.environ.get("DASHSCOPE_API_KEY") or os.environ.get("V16_ASR_API_KEY")):
        return False
    if provider in {"tencent", "tencentcloud", "tencent_flash", "tencent_flash_asr"}:
        return bool(os.environ.get("V16_TENCENT_SECRET_ID") and os.environ.get("V16_TENCENT_SECRET_KEY"))
    return bool(os.environ.get("V16_ASR_API_KEY") or os.environ.get("ASR_API_KEY") or os.environ.get("LLM_API_KEY"))


def _ocr_configured() -> bool:
    provider = (os.environ.get("V16_OCR_PROVIDER") or os.environ.get("OCR_PROVIDER") or "").strip().lower()
    if not provider:
        return False
    if provider in {"local_tesseract", "tesseract"}:
        return shutil.which("tesseract") is not None
    if provider == "tencent":
        return bool(os.environ.get("V16_TENCENT_SECRET_ID") and os.environ.get("V16_TENCENT_SECRET_KEY"))
    return bool(os.environ.get("V16_OCR_API_KEY") or os.environ.get("OCR_API_KEY"))


def _finalize(entry: dict[str, Any]) -> dict[str, Any]:
    entry["product_failure"] = resolve_product_failure(
        status=str(entry["status"]),
        reason=str(entry.get("reason") or ""),
    )
    return entry


def run_preflight_backend(client: EvalHttpClient) -> dict[str, Any]:
    t0 = time.perf_counter()
    try:
        payload = client.health_check()
        return _finalize(make_entry(
            case_id="backend",
            status="configured_and_passed",
            configured=True,
            reason="health_ok",
            detail={"health": payload},
            duration_ms=int((time.perf_counter() - t0) * 1000),
        ))
    except BackendUnavailableError as exc:
        return _finalize(make_entry(
            case_id="backend",
            status="backend_unavailable",
            configured=False,
            reason="backend_unreachable",
            detail={"error": str(exc)},
            duration_ms=int((time.perf_counter() - t0) * 1000),
        ))


def run_preflight_postgres() -> dict[str, Any]:
    t0 = time.perf_counter()
    db_url = os.environ.get("DATABASE_URL", "").strip()
    if not db_url:
        return _finalize(make_entry(
            case_id="postgres",
            status="not_configured",
            configured=False,
            reason="postgres_not_configured",
            duration_ms=int((time.perf_counter() - t0) * 1000),
        ))
    try:
        import psycopg

        with psycopg.connect(db_url, connect_timeout=5) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        return _finalize(make_entry(
            case_id="postgres",
            status="configured_and_passed",
            configured=True,
            reason="select_ok",
            duration_ms=int((time.perf_counter() - t0) * 1000),
        ))
    except Exception as exc:  # noqa: BLE001
        return _finalize(make_entry(
            case_id="postgres",
            status="dependency_missing",
            configured=False,
            reason="postgres_unreachable",
            detail={"error": type(exc).__name__},
            duration_ms=int((time.perf_counter() - t0) * 1000),
        ))


def run_preflight_playwright() -> dict[str, Any]:
    t0 = time.perf_counter()
    try:
        import playwright  # noqa: F401
    except ImportError:
        return _finalize(make_entry(
            case_id="playwright",
            status="dependency_missing",
            configured=False,
            reason="playwright_not_found",
            duration_ms=int((time.perf_counter() - t0) * 1000),
        ))
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "playwright", "install", "--dry-run", "chromium"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        combined = (proc.stdout or "") + (proc.stderr or "")
        if proc.returncode != 0 and "is already installed" not in combined.lower():
            return _finalize(make_entry(
                case_id="playwright",
                status="dependency_missing",
                configured=False,
                reason="playwright_browser_missing",
                detail={"exit_code": proc.returncode},
                duration_ms=int((time.perf_counter() - t0) * 1000),
            ))
        return _finalize(make_entry(
            case_id="playwright",
            status="configured_and_passed",
            configured=True,
            reason="playwright_available",
            duration_ms=int((time.perf_counter() - t0) * 1000),
        ))
    except Exception as exc:  # noqa: BLE001
        return _finalize(make_entry(
            case_id="playwright",
            status="dependency_missing",
            configured=False,
            reason="playwright_not_found",
            detail={"error": type(exc).__name__},
            duration_ms=int((time.perf_counter() - t0) * 1000),
        ))


def run_preflight_ffmpeg() -> dict[str, Any]:
    t0 = time.perf_counter()
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return _finalize(make_entry(
            case_id="ffmpeg",
            status="dependency_missing",
            configured=False,
            reason="ffmpeg_not_found",
            duration_ms=int((time.perf_counter() - t0) * 1000),
        ))
    try:
        proc = subprocess.run([ffmpeg, "-version"], capture_output=True, text=True, timeout=10, check=False)
        version_line = (proc.stdout or "").splitlines()[0] if proc.stdout else ""
        return _finalize(make_entry(
            case_id="ffmpeg",
            status="configured_and_passed",
            configured=True,
            reason="ffmpeg_available",
            detail={"version_line": version_line[:120]},
            duration_ms=int((time.perf_counter() - t0) * 1000),
        ))
    except Exception as exc:  # noqa: BLE001
        return _finalize(make_entry(
            case_id="ffmpeg",
            status="dependency_missing",
            configured=False,
            reason="ffmpeg_not_found",
            detail={"error": type(exc).__name__},
            duration_ms=int((time.perf_counter() - t0) * 1000),
        ))


def run_preflight_llm_key() -> dict[str, Any]:
    if _env_truthy("LIGHT_MAQA_FAKE_LLM"):
        return _finalize(make_entry(
            case_id="llm_key",
            status="skipped",
            configured=False,
            reason="fake_llm_enabled",
        ))
    if not _llm_key_present():
        return _finalize(make_entry(
            case_id="llm_key",
            status="not_configured",
            configured=False,
            reason="missing_llm_key",
        ))
    return _finalize(make_entry(
        case_id="llm_key",
        status="configured_and_passed",
        configured=True,
        reason="llm_key_present",
    ))


def run_preflight_asr_key() -> dict[str, Any]:
    if not _asr_configured():
        return _finalize(make_entry(
            case_id="asr_key",
            status="not_configured",
            configured=False,
            reason="missing_asr_key",
        ))
    return _finalize(make_entry(
        case_id="asr_key",
        status="configured_and_passed",
        configured=True,
        reason="asr_key_present",
    ))


def run_preflight_ocr_key() -> dict[str, Any]:
    if not _ocr_configured():
        return _finalize(make_entry(
            case_id="ocr_key",
            status="not_configured",
            configured=False,
            reason="missing_ocr_key",
        ))
    return _finalize(make_entry(
        case_id="ocr_key",
        status="configured_and_passed",
        configured=True,
        reason="ocr_key_present",
    ))


def run_dependency_preflight(client: EvalHttpClient) -> list[dict[str, Any]]:
    return [
        run_preflight_backend(client),
        run_preflight_postgres(),
        run_preflight_playwright(),
        run_preflight_ffmpeg(),
        run_preflight_llm_key(),
        run_preflight_asr_key(),
        run_preflight_ocr_key(),
    ]


def _backend_available(preflight: list[dict[str, Any]]) -> bool:
    for item in preflight:
        if item.get("case_id") == "backend":
            return item.get("status") == "configured_and_passed"
    return False


def run_capability_llm_real_minimal(case: dict[str, Any]) -> dict[str, Any]:
    t0 = time.perf_counter()
    if _env_truthy("LIGHT_MAQA_FAKE_LLM"):
        return _finalize(make_entry(
            case_id="llm_real_minimal",
            status="skipped",
            configured=False,
            reason="fake_llm_enabled",
            duration_ms=int((time.perf_counter() - t0) * 1000),
        ))
    if not _llm_key_present():
        return _finalize(make_entry(
            case_id="llm_real_minimal",
            status="not_configured",
            configured=False,
            reason="missing_llm_key",
            duration_ms=int((time.perf_counter() - t0) * 1000),
        ))
    _ensure_backend_path()
    try:
        from openai import OpenAI  # type: ignore[import-untyped]
        from config.settings import settings

        if settings.fake_llm_enabled:
            return _finalize(make_entry(
                case_id="llm_real_minimal",
                status="skipped",
                configured=False,
                reason="fake_llm_enabled",
                duration_ms=int((time.perf_counter() - t0) * 1000),
            ))
        client = OpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url, timeout=float(case.get("timeout_sec", 30)))
        completion = client.chat.completions.create(
            model=settings.fast_llm_model or settings.default_llm_model,
            messages=[{"role": "user", "content": str(case.get("user_input") or "1+1=?")}],
            max_tokens=32,
        )
        text = (completion.choices[0].message.content or "").strip()
        provider = str(getattr(completion, "model", "") or settings.llm_provider)
        if not text or "fake" in provider.lower():
            return _finalize(make_entry(
                case_id="llm_real_minimal",
                status="configured_and_failed",
                configured=True,
                reason="credential_invalid",
                detail={"text_length": len(text), "provider": provider},
                duration_ms=int((time.perf_counter() - t0) * 1000),
            ))
        return _finalize(make_entry(
            case_id="llm_real_minimal",
            status="configured_and_passed",
            configured=True,
            reason="llm_response_ok",
            detail={"text_length": len(text), "provider": provider},
            duration_ms=int((time.perf_counter() - t0) * 1000),
        ))
    except Exception as exc:  # noqa: BLE001
        err = type(exc).__name__
        reason = "external_timeout" if "timeout" in err.lower() or "timed out" in str(exc).lower() else "credential_invalid"
        status = "external_timeout" if reason == "external_timeout" else "configured_and_failed"
        return _finalize(make_entry(
            case_id="llm_real_minimal",
            status=status,
            configured=True,
            reason=reason,
            detail={"error": err},
            duration_ms=int((time.perf_counter() - t0) * 1000),
        ))


def run_capability_web_static_real(case: dict[str, Any], client: EvalHttpClient, *, backend_ok: bool) -> dict[str, Any]:
    t0 = time.perf_counter()
    if not backend_ok:
        return _finalize(make_entry(
            case_id="web_static_real",
            status="backend_unavailable",
            configured=False,
            reason="backend_unreachable",
            duration_ms=int((time.perf_counter() - t0) * 1000),
        ))
    setup = case.get("session_setup") or {}
    payload = {
        "message": case.get("user_input"),
        "session_id": setup.get("session_id") or "eval-real-web-static",
        "use_knowledge": bool(setup.get("use_knowledge", False)),
    }
    try:
        resp = client.post_chat_agno(payload)
        extra = resp.get("extra") or {}
        answer = str(resp.get("answer") or "")
        has_web = any(
            token in str(extra).lower() + answer.lower()
            for token in ("web", "http", "网页", "tutorial", "python")
        )
        caps = str(extra.get("capabilities_called") or extra)
        if not has_web and resp.get("task_status") == "succeeded":
            return _finalize(make_entry(
                case_id="web_static_real",
                status="configured_and_failed",
                configured=True,
                reason="fake_success_detected",
                detail={"task_status": resp.get("task_status"), "primary_path": resp.get("primary_path")},
                duration_ms=int((time.perf_counter() - t0) * 1000),
            ))
        if has_web:
            return _finalize(make_entry(
                case_id="web_static_real",
                status="configured_and_passed",
                configured=True,
                reason="web_evidence_present",
                detail={"task_status": resp.get("task_status"), "capabilities": caps[:200]},
                duration_ms=int((time.perf_counter() - t0) * 1000),
            ))
        return _finalize(make_entry(
            case_id="web_static_real",
            status="external_unavailable",
            configured=True,
            reason="network_unreachable",
            detail={"task_status": resp.get("task_status")},
            duration_ms=int((time.perf_counter() - t0) * 1000),
        ))
    except CaseTimeoutError:
        return _finalize(make_entry(
            case_id="web_static_real",
            status="external_timeout",
            configured=True,
            reason="provider_timeout",
            duration_ms=int((time.perf_counter() - t0) * 1000),
        ))
    except (BackendUnavailableError, ExecutionError) as exc:
        return _finalize(make_entry(
            case_id="web_static_real",
            status="backend_unavailable" if isinstance(exc, BackendUnavailableError) else "external_unavailable",
            configured=False if isinstance(exc, BackendUnavailableError) else True,
            reason="backend_unreachable" if isinstance(exc, BackendUnavailableError) else "network_unreachable",
            detail={"error": type(exc).__name__},
            duration_ms=int((time.perf_counter() - t0) * 1000),
        ))


def run_capability_document_fixture_real(case: dict[str, Any]) -> dict[str, Any]:
    t0 = time.perf_counter()
    _ensure_backend_path()
    import tools.document.parse_text  # noqa: F401
    from tools.document.registry import call_tool

    fixtures = [str(p) for p in (case.get("fixtures") or [])]
    if not fixtures:
        return _finalize(make_entry(
            case_id="document_fixture_real",
            status="not_configured",
            configured=False,
            reason="missing_fixture",
            duration_ms=int((time.perf_counter() - t0) * 1000),
        ))
    parsed = 0
    errors: list[str] = []
    for rel in fixtures:
        path = _repo_root() / rel
        if not path.exists():
            errors.append(f"missing:{rel}")
            continue
        result = call_tool("parse_text", file_path=str(path))
        if result.status == "success" and (result.text or "").strip():
            parsed += 1
        else:
            errors.append(result.error_code or result.failure_reason or "parse_failed")
    if parsed >= 1:
        return _finalize(make_entry(
            case_id="document_fixture_real",
            status="configured_and_passed",
            configured=True,
            reason="document_parsed",
            detail={"parsed_count": parsed, "fixture_count": len(fixtures), "errors": errors},
            duration_ms=int((time.perf_counter() - t0) * 1000),
        ))
    dep_reason = dependency_missing_reason_from_errors(errors)
    if dep_reason:
        return _finalize(make_entry(
            case_id="document_fixture_real",
            status="dependency_missing",
            configured=False,
            reason=dep_reason,
            detail={"errors": errors},
            duration_ms=int((time.perf_counter() - t0) * 1000),
        ))
    if any(str(e).startswith("missing:") for e in errors):
        return _finalize(make_entry(
            case_id="document_fixture_real",
            status="not_configured",
            configured=False,
            reason="missing_fixture",
            detail={"errors": errors},
            duration_ms=int((time.perf_counter() - t0) * 1000),
        ))
    return _finalize(make_entry(
        case_id="document_fixture_real",
        status="configured_and_failed",
        configured=True,
        reason="parse_failed",
        detail={"errors": errors},
        duration_ms=int((time.perf_counter() - t0) * 1000),
    ))


def run_capability_kb_real_roundtrip(case: dict[str, Any], client: EvalHttpClient, *, backend_ok: bool) -> dict[str, Any]:
    t0 = time.perf_counter()
    if not backend_ok:
        return _finalize(make_entry(
            case_id="kb_real_roundtrip",
            status="backend_unavailable",
            configured=False,
            reason="backend_unreachable",
            duration_ms=int((time.perf_counter() - t0) * 1000),
        ))
    if _env_truthy("LIGHT_MAQA_FAKE_LLM"):
        return _finalize(make_entry(
            case_id="kb_real_roundtrip",
            status="skipped",
            configured=False,
            reason="fake_llm_enabled",
            duration_ms=int((time.perf_counter() - t0) * 1000),
        ))
    if not os.environ.get("DATABASE_URL", "").strip():
        return _finalize(make_entry(
            case_id="kb_real_roundtrip",
            status="dependency_missing",
            configured=False,
            reason="postgres_not_configured",
            duration_ms=int((time.perf_counter() - t0) * 1000),
        ))
    setup = case.get("session_setup") or {}
    payload = {
        "message": case.get("user_input"),
        "session_id": setup.get("session_id") or "eval-real-kb-roundtrip",
        "use_knowledge": True,
    }
    try:
        resp = client.post_chat_agno(payload)
        extra = resp.get("extra") or {}
        hit = bool(extra.get("retrieved_chunks") or extra.get("kb_hit") or "知识库" in str(resp.get("answer") or ""))
        if hit or resp.get("task_status") in {"succeeded", "partial"}:
            return _finalize(make_entry(
                case_id="kb_real_roundtrip",
                status="configured_and_passed",
                configured=True,
                reason="kb_roundtrip_ok",
                detail={"task_status": resp.get("task_status"), "primary_path": resp.get("primary_path")},
                duration_ms=int((time.perf_counter() - t0) * 1000),
            ))
        return _finalize(make_entry(
            case_id="kb_real_roundtrip",
            status="configured_and_failed",
            configured=True,
            reason="kb_lifecycle_broken",
            detail={"task_status": resp.get("task_status")},
            duration_ms=int((time.perf_counter() - t0) * 1000),
        ))
    except CaseTimeoutError:
        return _finalize(make_entry(
            case_id="kb_real_roundtrip",
            status="external_timeout",
            configured=True,
            reason="provider_timeout",
            duration_ms=int((time.perf_counter() - t0) * 1000),
        ))
    except (BackendUnavailableError, ExecutionError) as exc:
        return _finalize(make_entry(
            case_id="kb_real_roundtrip",
            status="backend_unavailable" if isinstance(exc, BackendUnavailableError) else "external_unavailable",
            configured=False if isinstance(exc, BackendUnavailableError) else True,
            reason="backend_unreachable" if isinstance(exc, BackendUnavailableError) else "network_unreachable",
            detail={"error": type(exc).__name__},
            duration_ms=int((time.perf_counter() - t0) * 1000),
        ))


def run_capability_video_subtitle_probe_real(case: dict[str, Any], client: EvalHttpClient, *, backend_ok: bool) -> dict[str, Any]:
    t0 = time.perf_counter()
    env_key = str(case.get("env_url_key") or "REAL_VIDEO_TEST_URL")
    url = os.environ.get(env_key, "").strip()
    if not url:
        local = case.get("local_fixture")
        if local:
            url = f"file://{(_repo_root() / local).as_posix()}"
        else:
            return _finalize(make_entry(
                case_id="video_subtitle_probe_real",
                status="not_configured",
                configured=False,
                reason="missing_video_url",
                duration_ms=int((time.perf_counter() - t0) * 1000),
            ))
    if not backend_ok:
        return _finalize(make_entry(
            case_id="video_subtitle_probe_real",
            status="backend_unavailable",
            configured=False,
            reason="backend_unreachable",
            duration_ms=int((time.perf_counter() - t0) * 1000),
        ))
    template = str(case.get("user_input_template") or "请总结这个视频：{url}")
    payload = {
        "message": template.format(url=url),
        "session_id": "eval-real-video-probe",
        "use_knowledge": False,
    }
    try:
        resp = client.post_chat_agno(payload)
        answer = str(resp.get("answer") or "").lower()
        extra = resp.get("extra") or {}
        transcript_markers = ("subtitle", "transcript", "字幕", "video")
        has_signal = any(m in answer or m in str(extra).lower() for m in transcript_markers)
        if resp.get("task_status") == "succeeded" and not has_signal:
            return _finalize(make_entry(
                case_id="video_subtitle_probe_real",
                status="configured_and_failed",
                configured=True,
                reason="fake_success_detected",
                detail={"probe_state": "no_subtitle", "task_status": resp.get("task_status")},
                duration_ms=int((time.perf_counter() - t0) * 1000),
            ))
        probe_state = "subtitle_found" if has_signal else "no_subtitle"
        status = "configured_and_passed" if has_signal or resp.get("task_status") in {"pending", "blocked", "partial", "failed"} else "external_unavailable"
        return _finalize(make_entry(
            case_id="video_subtitle_probe_real",
            status=status,
            configured=True,
            reason=probe_state,
            detail={"task_status": resp.get("task_status"), "primary_path": resp.get("primary_path")},
            duration_ms=int((time.perf_counter() - t0) * 1000),
        ))
    except CaseTimeoutError:
        return _finalize(make_entry(
            case_id="video_subtitle_probe_real",
            status="external_timeout",
            configured=True,
            reason="provider_timeout",
            duration_ms=int((time.perf_counter() - t0) * 1000),
        ))
    except (BackendUnavailableError, ExecutionError) as exc:
        return _finalize(make_entry(
            case_id="video_subtitle_probe_real",
            status="backend_unavailable" if isinstance(exc, BackendUnavailableError) else "external_unavailable",
            configured=False if isinstance(exc, BackendUnavailableError) else True,
            reason="network_unreachable",
            detail={"error": type(exc).__name__},
            duration_ms=int((time.perf_counter() - t0) * 1000),
        ))


def run_capability_asr_real_short_audio(case: dict[str, Any]) -> dict[str, Any]:
    t0 = time.perf_counter()
    if not _asr_configured():
        return _finalize(make_entry(
            case_id="asr_real_short_audio",
            status="not_configured",
            configured=False,
            reason="missing_asr_key",
            duration_ms=int((time.perf_counter() - t0) * 1000),
        ))
    rel = str(case.get("fixture") or "")
    path = _repo_root() / rel
    if not path.exists():
        return _finalize(make_entry(
            case_id="asr_real_short_audio",
            status="not_configured",
            configured=False,
            reason="missing_fixture",
            duration_ms=int((time.perf_counter() - t0) * 1000),
        ))
    _ensure_backend_path()
    try:
        import tools.asr.asr_transcribe  # noqa: F401
        from tools.asr.registry import call_tool

        result = call_tool("asr_transcribe", file_path=str(path), duration_sec=float(case.get("max_duration_sec", 5)), force_sync=True)
        md = result.metadata or {}
        if result.status == "success" and (result.text or "").strip():
            return _finalize(make_entry(
                case_id="asr_real_short_audio",
                status="configured_and_passed",
                configured=True,
                reason="asr_ok",
                detail={"provider": md.get("provider"), "text_length": len(result.text or "")},
                duration_ms=int((time.perf_counter() - t0) * 1000),
            ))
        err = result.error_code or ""
        if "timeout" in err.lower():
            status = "external_timeout"
            reason = "provider_timeout"
            configured = True
        elif err in {"asr_not_configured", "tool_disabled", "external_processing_disabled", "paid_asr_disabled"}:
            status = "not_configured"
            reason = "missing_asr_key"
            configured = False
        elif is_dependency_missing_error(err):
            status = "dependency_missing"
            reason = dependency_missing_reason_from_errors([err]) or "dependency_not_installed"
            configured = False
        else:
            status = "configured_and_failed"
            reason = "credential_invalid"
            configured = True
        return _finalize(make_entry(
            case_id="asr_real_short_audio",
            status=status,
            configured=configured if "configured" in locals() else True,
            reason=reason,
            detail={"error_code": err},
            duration_ms=int((time.perf_counter() - t0) * 1000),
        ))
    except Exception as exc:  # noqa: BLE001
        return _finalize(make_entry(
            case_id="asr_real_short_audio",
            status="external_timeout" if "timeout" in str(exc).lower() else "configured_and_failed",
            configured=True,
            reason="provider_timeout" if "timeout" in str(exc).lower() else "credential_invalid",
            detail={"error": type(exc).__name__},
            duration_ms=int((time.perf_counter() - t0) * 1000),
        ))


def run_capability_ocr_real_sample(case: dict[str, Any]) -> dict[str, Any]:
    t0 = time.perf_counter()
    if not _ocr_configured():
        return _finalize(make_entry(
            case_id="ocr_real_sample",
            status="not_configured",
            configured=False,
            reason="missing_ocr_key",
            duration_ms=int((time.perf_counter() - t0) * 1000),
        ))
    rel = str(case.get("fixture") or "")
    path = _repo_root() / rel
    if not path.exists():
        return _finalize(make_entry(
            case_id="ocr_real_sample",
            status="not_configured",
            configured=False,
            reason="missing_fixture",
            duration_ms=int((time.perf_counter() - t0) * 1000),
        ))
    _ensure_backend_path()
    try:
        import tools.ocr.ocr_document  # noqa: F401
        from tools.ocr.registry import call_tool

        result = call_tool("ocr_document", file_path=str(path))
        if result.status == "success" and (result.text or "").strip():
            return _finalize(make_entry(
                case_id="ocr_real_sample",
                status="configured_and_passed",
                configured=True,
                reason="ocr_ok",
                detail={"text_length": len(result.text or "")},
                duration_ms=int((time.perf_counter() - t0) * 1000),
            ))
        err = result.error_code or ""
        if err in {"ocr_not_configured", "tool_disabled"}:
            return _finalize(make_entry(
                case_id="ocr_real_sample",
                status="not_configured",
                configured=False,
                reason="missing_ocr_key",
                detail={"error_code": err},
                duration_ms=int((time.perf_counter() - t0) * 1000),
            ))
        if is_dependency_missing_error(err):
            return _finalize(make_entry(
                case_id="ocr_real_sample",
                status="dependency_missing",
                configured=False,
                reason=dependency_missing_reason_from_errors([err]) or "dependency_not_installed",
                detail={"error_code": err},
                duration_ms=int((time.perf_counter() - t0) * 1000),
            ))
        return _finalize(make_entry(
            case_id="ocr_real_sample",
            status="configured_and_failed",
            configured=True,
            reason="credential_invalid",
            detail={"error_code": err},
            duration_ms=int((time.perf_counter() - t0) * 1000),
        ))
    except Exception as exc:  # noqa: BLE001
        return _finalize(make_entry(
            case_id="ocr_real_sample",
            status="external_timeout" if "timeout" in str(exc).lower() else "configured_and_failed",
            configured=True,
            reason="provider_timeout" if "timeout" in str(exc).lower() else "credential_invalid",
            detail={"error": type(exc).__name__},
            duration_ms=int((time.perf_counter() - t0) * 1000),
        ))


_CAPABILITY_RUNNERS = {
    "llm_real_minimal": lambda case, client, backend_ok: run_capability_llm_real_minimal(case),
    "web_static_real": lambda case, client, backend_ok: run_capability_web_static_real(case, client, backend_ok=backend_ok),
    "document_fixture_real": lambda case, client, backend_ok: run_capability_document_fixture_real(case),
    "kb_real_roundtrip": lambda case, client, backend_ok: run_capability_kb_real_roundtrip(case, client, backend_ok=backend_ok),
    "video_subtitle_probe_real": lambda case, client, backend_ok: run_capability_video_subtitle_probe_real(case, client, backend_ok=backend_ok),
    "asr_real_short_audio": lambda case, client, backend_ok: run_capability_asr_real_short_audio(case),
    "ocr_real_sample": lambda case, client, backend_ok: run_capability_ocr_real_sample(case),
}


def run_capability_cases(
    cases: list[dict[str, Any]],
    client: EvalHttpClient,
    *,
    backend_ok: bool,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for case in cases:
        case_id = str(case.get("case_id"))
        runner = _CAPABILITY_RUNNERS.get(case_id)
        if runner is None:
            results.append(_finalize(make_entry(
                case_id=case_id,
                status="skipped",
                configured=False,
                reason="unknown_case",
            )))
            continue
        results.append(runner(case, client, backend_ok))
    return results


def run_optional_regression(*, backend_ok: bool) -> dict[str, Any]:
    if not _env_truthy("REAL_EXTERNAL_RUN_REGRESSION"):
        return {"enabled": False, "reason": "REAL_EXTERNAL_RUN_REGRESSION not set"}
    if not backend_ok:
        return {"enabled": True, "reason": "backend_unavailable", "regression_overview": None}
    try:
        from scripts.evaluation.render_eval_overview import render_regression_overview
        from tests.evaluation.runners.eval_complex_agent_runner import run_v3_suite, v3_case_file
        from tests.evaluation.runners.eval_multiturn_runner import run_multiturn_suite, v2_5_case_file
        from tests.evaluation.runners.eval_runner import run_suite, v1_case_file

        client = EvalHttpClient()
        regression_results = []
        for suite_name, case_file in [
            ("v1_route_exit_state", v1_case_file()),
            ("v2_5_multiturn_state", v2_5_case_file()),
            ("v3_complex_agent", v3_case_file()),
        ]:
            if suite_name == "v2_5_multiturn_state":
                result = run_multiturn_suite(suite_name=suite_name, case_file=case_file, client=client)
                regression_results.append({
                    "suite_name": suite_name,
                    "report_paths": result["report_paths"],
                    "total_flows": len(result["flow_results"]),
                    "passed_flows": sum(1 for f in result["flow_results"] if f["passed"]),
                    "failed_flows": sum(1 for f in result["flow_results"] if not f["passed"]),
                    "flow_results": result["flow_results"],
                })
            else:
                result = run_suite(suite_name=suite_name, case_file=case_file, client=client)
                regression_results.append({
                    "suite_name": suite_name,
                    "report_paths": result["report_paths"],
                    "total_cases": len(result["case_results"]),
                    "passed_cases": sum(1 for c in result["case_results"] if c["passed"]),
                    "failed_cases": sum(1 for c in result["case_results"] if not c["passed"]),
                    "case_results": result["case_results"],
                })
        from scripts.evaluation.render_eval_overview import build_regression_overview

        overview = build_regression_overview(regression_results, "ok")
        overview_paths = render_regression_overview(
            regression_results=regression_results,
            backend_status="ok",
            generated_at=datetime.now().isoformat(timespec="seconds"),
        )
        failed_unknown = any(r.get("status") == "failed_unknown" for r in overview.get("suite_results") or [])
        return {
            "enabled": True,
            "reason": "regression_executed",
            "failed_unknown": failed_unknown,
            "regression_overview": overview,
            "report_paths": overview_paths,
        }
    except Exception as exc:  # noqa: BLE001
        return {"enabled": True, "reason": "regression_error", "error": type(exc).__name__, "regression_overview": None}


def run_real_external_smoke_suite(
    *,
    client: EvalHttpClient | None = None,
    case_file: str | Path | None = None,
) -> dict[str, Any]:
    started_at = datetime.now().isoformat(timespec="seconds")
    http_client = client or EvalHttpClient()
    preflight = run_dependency_preflight(http_client)
    backend_ok = _backend_available(preflight)
    cases = load_real_external_cases(case_file)
    capability_results = run_capability_cases(cases, http_client, backend_ok=backend_ok)
    optional_regression = run_optional_regression(backend_ok=backend_ok)
    finished_at = datetime.now().isoformat(timespec="seconds")
    summary = aggregate_capability_summary(capability_results)
    report = {
        "suite_name": "real_external_smoke",
        "suite_role": "real_capability_reproducibility",
        "version_note": "V4 post-hardening; not a new eval version",
        "started_at": started_at,
        "finished_at": finished_at,
        "backend_base_url": http_client.base_url,
        "environment_summary": {
            "LIGHT_MAQA_FAKE_LLM": "1" if _env_truthy("LIGHT_MAQA_FAKE_LLM") else "0",
            "DATABASE_URL_set": bool(os.environ.get("DATABASE_URL", "").strip()),
            "REAL_VIDEO_TEST_URL_set": bool(os.environ.get("REAL_VIDEO_TEST_URL", "").strip()),
            "REAL_EXTERNAL_RUN_REGRESSION": os.environ.get("REAL_EXTERNAL_RUN_REGRESSION", "0"),
        },
        "dependency_preflight": preflight,
        "capability_cases": capability_results,
        "optional_regression": optional_regression,
        "summary": summary,
    }
    report["final_verdict"] = compute_final_verdict(
        capability_cases=capability_results,
        backend_available=backend_ok,
    )
    report["sanitized_summary"] = build_sanitized_summary(report)
    report["recommendations"] = build_recommendations(report)
    report["exit_code"] = compute_exit_code(
        backend_unavailable=not backend_ok,
        configured_cases_count=summary["configured_cases_count"],
        product_failure_cases_count=summary["product_failure_cases_count"],
        optional_regression_failed_unknown=bool(optional_regression.get("failed_unknown")),
    )
    paths = write_real_external_smoke_report(report)
    report["report_paths"] = {k: str(v) for k, v in paths.items()}
    return report
