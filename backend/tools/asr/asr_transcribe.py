from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from config.settings import settings
from storage import task_job_store
from tasks.orchestration.task_store import create_task_record
from tools.asr import errors as asr_errors
from tools.asr.providers import (
    AsrProviderOutcome,
    run_dashscope_asr,
    run_fixture_asr,
    run_generic_http_asr,
    run_local_faster_whisper,
    run_local_whisper,
    run_tencent_asr,
    run_tencent_flash_asr,
)
from tools.asr.registry import AsrToolSchema, register
from tools.document.tool_result import DocumentToolResult

_OPENAI_COMPAT = frozenset({"siliconflow", "openai", "openai_whisper"})
_CLOUD = frozenset(
    {
        "generic_http",
        "remote",
        "dashscope",
        "tencent",
        "tencentcloud",
        "tencent_flash",
        "tencent_flash_asr",
        *_OPENAI_COMPAT,
    }
)
_FIXTURE = frozenset({"mock", "fake"})
_LOCAL = frozenset({"local_whisper", "faster_whisper"})
_SUPPORTED = _CLOUD | _FIXTURE | _LOCAL


def _resolved_asr_provider() -> str:
    v = (getattr(settings, "v16_asr_provider", None) or "").strip().lower()
    if v:
        return v
    return (settings.asr_provider or "").strip().lower()


def _normalized_provider_chain(provider_chain: list[str] | tuple[str, ...] | None) -> tuple[str, ...]:
    if provider_chain:
        ordered = tuple(str(p).strip().lower() for p in provider_chain if str(p).strip())
        if ordered:
            return ordered
    base = _resolved_asr_provider()
    return (base,) if base else ()


def _asr_max_file_bytes() -> int:
    mb = int(getattr(settings, "v16_asr_max_file_mb", 0) or 0)
    if mb <= 0:
        mb = int(getattr(settings, "asr_max_file_mb", 50) or 50)
    return mb * 1024 * 1024


def _duration_limits_exceeded(duration_sec: float) -> tuple[bool, str]:
    if not duration_sec or duration_sec <= 0:
        return False, ""
    extra = int(getattr(settings, "v16_asr_max_duration_sec", 0) or 0)
    if extra > 0 and duration_sec > extra:
        return True, asr_errors.ASR_DURATION_LIMIT_EXCEEDED
    if duration_sec > settings.v16_max_video_duration_sec:
        return True, asr_errors.VIDEO_TOO_LONG
    return False, ""


def _r5c_duration_decision(
    duration_sec: float,
    *,
    user_confirmed: bool,
) -> tuple[str, str, str]:
    """三段时长规则（≤15min / 15–120min / >2h）。

    返回 (decision, error_code, reason):
      - decision="allow"        ：≤ short_threshold（默认 900s/15min），直接 ASR
      - decision="needs_confirm"：short < 时长 ≤ long（900-7200s），且未带 user_confirmed → 拒绝调用外部 API
      - decision="reject"       ：> long_threshold（>7200s/>2h），按硬上限拒绝
    """
    if not duration_sec or duration_sec <= 0:
        return "allow", "", ""
    short_thr = int(getattr(settings, "v16_asr_short_threshold_sec", 900) or 900)
    long_thr = int(getattr(settings, "v16_asr_long_threshold_sec", 7200) or 7200)
    if duration_sec > long_thr:
        return (
            "reject",
            asr_errors.ASR_DURATION_LIMIT_EXCEEDED,
            f"媒体时长 {int(duration_sec)}s 超过 V16 ASR 硬上限 {long_thr}s（> 2 小时）",
        )
    if duration_sec > short_thr and not user_confirmed:
        return (
            "needs_confirm",
            asr_errors.ASR_REQUIRES_USER_CONFIRMATION,
            f"媒体时长 {int(duration_sec)}s 超过短音频阈值 {short_thr}s（>15 分钟），调用前必须 user_confirmed=True",
        )
    return "allow", "", ""


def _failed(
    task_id: str,
    *,
    error_code: str,
    failure_reason: str,
    next_action_hint: str = "",
    duration_ms: float = 0.0,
    meta: dict | None = None,
) -> DocumentToolResult:
    task_job_store.mark_task_failed(task_id, error_code=error_code, failure_reason=failure_reason)
    md = {
        "source_type": "asr_transcript",
        "provider": "",
        "provider_type": "",
        "production_ready": False,
        "external_processing": False,
        "estimated_cost": 0.0,
        "segments": [],
    }
    if meta:
        md.update(meta)
    return DocumentToolResult(
        tool_name="asr_transcribe",
        source_type="asr_transcript",
        task_id=task_id,
        status="failed",
        error_code=error_code,
        failure_reason=failure_reason,
        next_action_hint=next_action_hint,
        duration_ms=duration_ms,
        metadata=md,
        quality={"quality_level": "failed", "text_length": 0},
        trace=[f"v16:asr failed code={error_code}"],
    )


def _queued_async(
    task_id: str,
    *,
    duration_sec: float,
    session_id: str = "",
) -> DocumentToolResult:
    short_thr = int(getattr(settings, "v16_asr_short_threshold_sec", 900) or 900)
    long_thr = int(getattr(settings, "v16_asr_long_threshold_sec", 7200) or 7200)
    md = {
        "source_type": "asr_transcript",
        "provider": "tencent_async",
        "provider_type": "tencent_async",
        "production_ready": False,
        "external_processing": True,
        "estimated_cost": 0.0,
        "segments": [],
        "duration_sec": float(duration_sec or 0.0),
        "v16_asr_short_threshold_sec": short_thr,
        "v16_asr_long_threshold_sec": long_thr,
        "decision": "queued_async",
        "async_mode": "create_rec_task_pending",
        "user_confirmed": True,
        "session_id": session_id,
    }
    return DocumentToolResult(
        tool_name="asr_transcribe",
        source_type="asr_transcript",
        task_id=task_id,
        status="queued",
        error_code="",
        failure_reason="",
        next_action_hint="长音频已确认，等待异步 ASR 任务完成后再生成 transcript / pending。",
        metadata=md,
        quality={"quality_level": "queued", "text_length": 0},
        trace=["v16:asr queued_async awaiting_provider_task"],
    )


def _asr_transcribe(
    file_path: str,
    *,
    duration_sec: float = 0.0,
    estimated_cost: float = 0.0,
    session_id: str = "",
    user_confirmed: bool = False,
    force_sync: bool = False,
    provider_chain: list[str] | tuple[str, ...] | None = None,
    deadline_ms: int = 0,
) -> DocumentToolResult:
    t0 = time.perf_counter()
    task_id = create_task_record(
        task_type="asr_transcribe",
        source_type="asr_transcript",
        session_id=session_id,
        user_query=file_path,
    )
    if not settings.v16_enable_asr:
        task_job_store.mark_task_failed(
            task_id,
            error_code="tool_disabled",
            failure_reason="asr tool disabled",
        )
        return DocumentToolResult(
            tool_name="asr_transcribe",
            source_type="asr_transcript",
            task_id=task_id,
            status="failed",
            error_code="tool_disabled",
            failure_reason="asr tool disabled",
        )

    path = Path(file_path)
    if not path.exists():
        return _failed(
            task_id,
            error_code="file_not_found",
            failure_reason=f"文件不存在: {file_path}",
            next_action_hint="确认路径",
            duration_ms=(time.perf_counter() - t0) * 1000.0,
        )
    try:
        sz = path.stat().st_size
    except OSError as e:
        return _failed(
            task_id,
            error_code=asr_errors.ASR_PROVIDER_ERROR,
            failure_reason=f"无法读取文件: {e}",
            duration_ms=(time.perf_counter() - t0) * 1000.0,
        )
    lim = _asr_max_file_bytes()
    if sz > lim:
        return _failed(
            task_id,
            error_code=asr_errors.ASR_FILE_TOO_LARGE,
            failure_reason="ASR 输入文件超过大小上限",
            next_action_hint="提高 V16_ASR_MAX_FILE_MB 或 ASR_MAX_FILE_MB",
            duration_ms=(time.perf_counter() - t0) * 1000.0,
            meta={"file_size": sz},
        )

    # 三段时长规则（≤15min 直进 / 15–120min 需 user_confirmed / >2h 拒绝）。
    decision, dec_code, dec_reason = _r5c_duration_decision(
        duration_sec, user_confirmed=user_confirmed
    )
    if decision != "allow":
        hint = (
            "重新调用并显式传入 user_confirmed=True"
            if decision == "needs_confirm"
            else "拆分音频/视频后再次提交，或调高 V16_ASR_LONG_THRESHOLD_SEC（不推荐）"
        )
        return _failed(
            task_id,
            error_code=dec_code,
            failure_reason=dec_reason or "媒体时长不在 V16 ASR 允许范围",
            next_action_hint=hint,
            duration_ms=(time.perf_counter() - t0) * 1000.0,
            meta={
                "duration_sec": float(duration_sec or 0.0),
                "v16_asr_short_threshold_sec": int(
                    getattr(settings, "v16_asr_short_threshold_sec", 900) or 900
                ),
                "v16_asr_long_threshold_sec": int(
                    getattr(settings, "v16_asr_long_threshold_sec", 7200) or 7200
                ),
                "decision": decision,
            },
        )
    short_thr = int(getattr(settings, "v16_asr_short_threshold_sec", 900) or 900)
    long_thr = int(getattr(settings, "v16_asr_long_threshold_sec", 7200) or 7200)
    if duration_sec > short_thr and duration_sec <= long_thr and user_confirmed and not force_sync:
        return _queued_async(
            task_id,
            duration_sec=duration_sec,
            session_id=session_id,
        )

    # 旧的 v16_asr_max_duration_sec / v16_max_video_duration_sec 仍作为可选硬限保留。
    task_job_store.mark_task_running(task_id, stage="asr_gate")
    bad_dur, dur_code = _duration_limits_exceeded(duration_sec)
    if bad_dur:
        return _failed(
            task_id,
            error_code=dur_code,
            failure_reason="媒体时长超过 ASR 限制",
            duration_ms=(time.perf_counter() - t0) * 1000.0,
            meta={"duration_sec": float(duration_sec or 0.0)},
        )

    provider_order = _normalized_provider_chain(provider_chain)
    if not provider_order:
        return _failed(
            task_id,
            error_code=asr_errors.ASR_NOT_CONFIGURED,
            failure_reason="未配置可用的 V16 ASR provider",
            next_action_hint=(
                "设置 V16_ASR_PROVIDER=tencent_flash / tencent / generic_http / "
                "local_whisper / mock，并确认相关 key 已写入 .env"
            ),
            duration_ms=(time.perf_counter() - t0) * 1000.0,
        )

    if estimated_cost > settings.v16_max_asr_cost_per_task:
        return _failed(
            task_id,
            error_code=asr_errors.BUDGET_EXCEEDED,
            failure_reason="ASR 预算超限",
            next_action_hint="降低预估成本或提高 V16_ASR_MAX_COST_PER_TASK",
            duration_ms=(time.perf_counter() - t0) * 1000.0,
            meta={"estimated_cost": estimated_cost},
        )

    if any(provider in _CLOUD for provider in provider_order):
        if not settings.v16_enable_external_processing:
            return _failed(
                task_id,
                error_code=asr_errors.EXTERNAL_PROCESSING_DISABLED,
                failure_reason="外部 ASR 处理未授权",
                next_action_hint="设置 V16_ENABLE_EXTERNAL_PROCESSING=1",
                duration_ms=(time.perf_counter() - t0) * 1000.0,
            )
        if not settings.v16_enable_paid_asr:
            return _failed(
                task_id,
                error_code=asr_errors.PAID_ASR_DISABLED,
                failure_reason="付费 ASR 未开启",
                next_action_hint="设置 V16_ENABLE_PAID_ASR=1",
                duration_ms=(time.perf_counter() - t0) * 1000.0,
            )

    provider = ""
    out: AsrProviderOutcome | None = None
    provider_failures: list[dict[str, str]] = []
    provider_attempts: list[dict[str, Any]] = []
    for candidate in provider_order:
        provider = candidate
        if provider not in _SUPPORTED:
            provider_failures.append({"provider": provider, "error": "unsupported_provider"})
            provider_attempts.append(
                {"provider": provider, "ok": False, "error": "unsupported_provider", "duration_ms": 0}
            )
            continue
        if deadline_ms > 0 and ((time.perf_counter() - t0) * 1000.0) >= deadline_ms:
            provider_failures.append({"provider": provider, "error": "deadline_exhausted"})
            provider_attempts.append(
                {"provider": provider, "ok": False, "error": "deadline_exhausted", "duration_ms": 0}
            )
            break
        provider_started = time.perf_counter()
        if provider in _OPENAI_COMPAT:
            from llm.asr import transcribe_audio

            compat = transcribe_audio(path, provider_override=provider)
            out = AsrProviderOutcome(
                ok=bool(getattr(compat, "available", False) and (getattr(compat, "text", "") or "").strip()),
                text=(getattr(compat, "text", "") or "").strip(),
                segments=[],
                error_code=asr_errors.ASR_PROVIDER_ERROR if not getattr(compat, "available", False) else "",
                failure_reason=(getattr(compat, "error", "") or "").strip(),
                next_action_hint=(
                    "检查 .env 中的 ASR_PROVIDER / ASR_BASE_URL / LLM_API_KEY，"
                    "或确认网络与额度"
                ),
                provider_type=str(getattr(compat, "provider", "") or provider),
                production_ready=True,
                external_processing=True,
            )
        elif provider in {"tencent", "tencentcloud"}:
            out = run_tencent_asr(
                path,
                secret_id=settings.v16_tencent_secret_id,
                secret_key=settings.v16_tencent_secret_key,
                region=settings.v16_tencent_region,
                engine_model_type=settings.v16_tencent_asr_engine_model_type,
                timeout_sec=float(settings.v16_asr_timeout_sec or 120.0),
            )
        elif provider in {"tencent_flash", "tencent_flash_asr"}:
            out = run_tencent_flash_asr(
                path,
                appid=settings.v16_tencent_appid,
                secret_id=settings.v16_tencent_secret_id,
                secret_key=settings.v16_tencent_secret_key,
                engine_model_type=settings.v16_tencent_asr_engine_model_type,
                timeout_sec=float(settings.v16_asr_timeout_sec or 120.0),
            )
        elif provider == "dashscope":
            out = run_dashscope_asr(
                path,
                api_key=settings.dashscope_api_key or settings.v16_asr_api_key,
                model=settings.asr_model or "paraformer-v2",
                timeout_sec=float(settings.v16_asr_timeout_sec or 120.0),
            )
        elif provider in _FIXTURE:
            out = run_fixture_asr(path)
        elif provider == "local_whisper":
            out = run_local_whisper(path, model_name=settings.asr_model or "tiny")
        elif provider == "faster_whisper":
            out = run_local_faster_whisper(path, model_size=settings.asr_model or "tiny")
        else:
            ep = (settings.v16_asr_endpoint or "").strip()
            if not ep:
                provider_failures.append({"provider": provider, "error": "missing_endpoint"})
                provider_attempts.append(
                    {"provider": provider, "ok": False, "error": "missing_endpoint", "duration_ms": 0}
                )
                continue
            out = run_generic_http_asr(
                path,
                endpoint=ep,
                api_key=settings.v16_asr_api_key or "",
                timeout_sec=float(settings.v16_asr_timeout_sec or 120.0),
            )
        attempt_duration_ms = max(
            int((time.perf_counter() - provider_started) * 1000),
            int(getattr(out, "duration_ms", 0.0) or 0.0),
        )
        provider_attempts.append(
            {
                "provider": provider,
                "provider_type": getattr(out, "provider_type", "") or provider,
                "ok": bool(out.ok and (out.text or "").strip()),
                "duration_ms": attempt_duration_ms,
                "error_code": getattr(out, "error_code", "") or "",
                "failure_reason": getattr(out, "failure_reason", "") or "",
                "http_status": int(getattr(out, "http_status", 0) or 0),
                "response_snippet": str(getattr(out, "response_snippet", "") or "")[:240],
            }
        )
        if out.ok and (out.text or "").strip():
            break
        provider_failures.append({"provider": provider, "error": out.error_code or out.failure_reason or "provider_failed"})
        out = None

    if out is None:
        return _failed(
            task_id,
            error_code=asr_errors.ASR_PROVIDER_ERROR,
            failure_reason="全部 ASR provider 均失败",
            next_action_hint="检查 provider 顺序、额度、网络与 Secret/Key 配置",
            duration_ms=(time.perf_counter() - t0) * 1000.0,
            meta={
                "provider_failures": provider_failures,
                "provider_attempts": provider_attempts,
                "provider_chain": list(provider_order),
            },
        )

    elapsed = (time.perf_counter() - t0) * 1000.0
    duration_ms = max(elapsed, out.duration_ms)
    if not out.ok:
        task_job_store.mark_task_failed(
            task_id,
            error_code=out.error_code,
            failure_reason=out.failure_reason,
        )
        return DocumentToolResult(
            tool_name="asr_transcribe",
            source_type="asr_transcript",
            task_id=task_id,
            status="failed",
            error_code=out.error_code,
            failure_reason=out.failure_reason,
            next_action_hint=out.next_action_hint,
            duration_ms=duration_ms,
            metadata={
                "source_type": "asr_transcript",
                "file_path": str(path),
                "provider": provider,
                "provider_type": out.provider_type,
                "production_ready": out.production_ready,
                "external_processing": out.external_processing,
                "estimated_cost": estimated_cost,
                "duration_sec": duration_sec,
                "segments": [],
                "provider_failures": provider_failures,
                "provider_attempts": provider_attempts,
                "provider_chain": list(provider_order),
            },
            quality={"quality_level": "failed", "text_length": 0},
            trace=[f"v16:asr err provider={provider} code={out.error_code}"],
        )

    task_job_store.mark_task_succeeded(
        task_id,
        result_summary={"status": "success", "text_length": len(out.text)},
        result_source_id=str(path),
    )
    md = {
        "source_type": "asr_transcript",
        "file_path": str(path),
        "provider": provider,
        "provider_type": out.provider_type,
        "production_ready": out.production_ready,
        "external_processing": out.external_processing,
        "estimated_cost": estimated_cost,
        "cost_used": estimated_cost,
        "duration_sec": duration_sec,
        "segments": out.segments,
        "provider_failures": provider_failures,
        "provider_attempts": provider_attempts,
        "provider_chain": list(provider_order),
    }
    return DocumentToolResult(
        tool_name="asr_transcribe",
        source_type="asr_transcript",
        task_id=task_id,
        status="success",
        text=out.text,
        structured_data={"segments": out.segments},
        metadata=md,
        quality={"quality_level": "usable", "text_length": len(out.text)},
        duration_ms=duration_ms,
        trace=[f"v16:asr ok provider={provider} type={out.provider_type} len={len(out.text)}"],
    )


register(
    AsrToolSchema(
        tool_name="asr_transcribe",
        description=(
            "ASR tool: generic HTTP / local whisper / fixture; gates for external, paid, "
            "budget, size, duration."
        ),
        input_schema={
            "type": "object",
            "required": ["file_path"],
            "properties": {"file_path": {"type": "string"}},
        },
        output_schema={
            "type": "object",
            "properties": {"status": {"type": "string"}, "text": {"type": "string"}},
        },
        call_fn=_asr_transcribe,
        enabled=True,
    )
)
