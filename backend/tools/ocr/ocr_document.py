from __future__ import annotations

import time
from pathlib import Path

from config.settings import settings
from storage import task_job_store
from tasks.orchestration.task_store import create_task_record
from tools.document.limits import MAX_FILE_BYTES, MAX_PDF_PAGES
from tools.document.tool_result import DocumentToolResult
from tools.ocr import errors as ocr_errors
from tools.ocr.providers import (
    OcrProviderOutcome,
    run_fixture_ocr,
    run_generic_http_ocr,
    run_local_tesseract,
    run_tencent_ocr,
)
from tools.ocr.registry import OcrToolSchema, register

_CLOUD_PROVIDERS = frozenset({"generic_http", "remote", "tencent", "tencentcloud"})
_FIXTURE_PROVIDERS = frozenset({"mock", "fake"})
_FALLBACK_ELIGIBLE_ERRORS = frozenset(
    {
        ocr_errors.OCR_PROVIDER_ERROR,
        ocr_errors.OCR_INVALID_RESPONSE,
        ocr_errors.OCR_EMPTY_RESULT,
    }
)


def _local_tesseract_fallback_allowed(path: Path, primary_out: OcrProviderOutcome) -> bool:
    provider = (settings.v16_ocr_provider or "").strip().lower()
    if provider not in {"tencent", "tencentcloud"}:
        return False
    if path.suffix.lower() == ".pdf":
        return False
    if primary_out.ok:
        return False
    return (primary_out.error_code or "") in _FALLBACK_ELIGIBLE_ERRORS


def _pdf_page_count(path: Path) -> int | None:
    if path.suffix.lower() != ".pdf":
        return None
    try:
        import fitz  # type: ignore[import-untyped]
    except ImportError:
        return None
    try:
        doc = fitz.open(path)
        n = doc.page_count
        doc.close()
        return int(n)
    except (ValueError, OSError, RuntimeError):
        return None


def _failed(
    task_id: str,
    *,
    error_code: str,
    failure_reason: str,
    next_action_hint: str = "",
    duration_ms: float = 0.0,
    metadata: dict | None = None,
) -> DocumentToolResult:
    task_job_store.mark_task_failed(task_id, error_code=error_code, failure_reason=failure_reason)
    meta = {
        "source_type": "ocr_document",
        "provider": "",
        "provider_type": "",
        "production_ready": False,
        "external_processing": False,
        "estimated_cost": 0.0,
        "pages": [],
    }
    if metadata:
        meta.update(metadata)
    return DocumentToolResult(
        tool_name="ocr_document",
        source_type="ocr_document",
        task_id=task_id,
        status="failed",
        error_code=error_code,
        failure_reason=failure_reason,
        next_action_hint=next_action_hint,
        duration_ms=duration_ms,
        metadata=meta,
        quality={"quality_level": "failed", "text_length": 0},
        trace=[f"v16:ocr failed code={error_code}"],
    )


def _ocr_document(
    file_path: str, *, estimated_cost: float = 0.0, session_id: str = ""
) -> DocumentToolResult:
    t0 = time.perf_counter()
    task_id = create_task_record(
        task_type="ocr_document",
        source_type="ocr_document",
        session_id=session_id,
        user_query=file_path,
    )
    task_job_store.mark_task_running(task_id, stage="ocr_gate")

    if not settings.v16_enable_ocr:
        task_job_store.mark_task_failed(task_id, error_code="tool_disabled", failure_reason="ocr tool disabled")
        return DocumentToolResult(
            tool_name="ocr_document",
            source_type="ocr_document",
            task_id=task_id,
            status="failed",
            error_code="tool_disabled",
            failure_reason="ocr tool disabled",
        )

    path = Path(file_path)
    if not path.exists():
        return _failed(
            task_id,
            error_code="file_not_found",
            failure_reason=f"文件不存在: {file_path}",
            next_action_hint="确认路径有效",
            duration_ms=(time.perf_counter() - t0) * 1000.0,
        )

    try:
        sz = path.stat().st_size
    except OSError as e:
        return _failed(
            task_id,
            error_code="ocr_provider_error",
            failure_reason=f"无法读取文件: {e}",
            duration_ms=(time.perf_counter() - t0) * 1000.0,
        )

    if sz > MAX_FILE_BYTES:
        return _failed(
            task_id,
            error_code=ocr_errors.OCR_FILE_TOO_LARGE,
            failure_reason="OCR 输入文件超过大小上限",
            next_action_hint=f"限制见 V16_MAX_FILE_MB（当前 {MAX_FILE_BYTES} 字节）",
            duration_ms=(time.perf_counter() - t0) * 1000.0,
            metadata={"file_path": str(path), "file_size": sz},
        )

    pc = _pdf_page_count(path)
    if pc is not None and pc > MAX_PDF_PAGES:
        return _failed(
            task_id,
            error_code=ocr_errors.OCR_PAGE_LIMIT_EXCEEDED,
            failure_reason=f"PDF 页数 {pc} 超过上限 {MAX_PDF_PAGES}",
            next_action_hint="拆分 PDF 或提高 V16_MAX_PDF_PAGES",
            duration_ms=(time.perf_counter() - t0) * 1000.0,
            metadata={"page_count": pc},
        )

    provider = (settings.v16_ocr_provider or "").strip().lower()
    if not provider:
        return _failed(
            task_id,
            error_code=ocr_errors.OCR_NOT_CONFIGURED,
            failure_reason="未配置 OCR provider",
            next_action_hint="配置 V16_OCR_PROVIDER（generic_http / local_tesseract / mock）",
            duration_ms=(time.perf_counter() - t0) * 1000.0,
        )

    if estimated_cost > settings.v16_max_ocr_cost_per_task:
        return _failed(
            task_id,
            error_code=ocr_errors.BUDGET_EXCEEDED,
            failure_reason="OCR 预算超限",
            next_action_hint="降低预估成本或提高 V16_OCR_MAX_COST_PER_TASK",
            duration_ms=(time.perf_counter() - t0) * 1000.0,
            metadata={"estimated_cost": estimated_cost},
        )

    # ── 外部云 OCR：external + paid ──────────────────────────────────────
    fallback_warning = ""
    fallback_provider = ""
    if provider in _CLOUD_PROVIDERS:
        if not settings.v16_enable_external_processing:
            return _failed(
                task_id,
                error_code=ocr_errors.EXTERNAL_PROCESSING_DISABLED,
                failure_reason="外部 OCR 处理未授权（ENABLE_EXTERNAL_PROCESSING / V16_ENABLE_EXTERNAL_PROCESSING）",
                next_action_hint="设置 V16_ENABLE_EXTERNAL_PROCESSING=1",
                duration_ms=(time.perf_counter() - t0) * 1000.0,
            )
        if not settings.v16_enable_paid_ocr:
            return _failed(
                task_id,
                error_code=ocr_errors.PAID_OCR_DISABLED,
                failure_reason="付费 OCR 未开启",
                next_action_hint="设置 V16_ENABLE_PAID_OCR=1",
                duration_ms=(time.perf_counter() - t0) * 1000.0,
            )
        if provider in {"tencent", "tencentcloud"}:
            is_pdf_input = path.suffix.lower() == ".pdf"
            if is_pdf_input:
                # V16-r5b：扫描 PDF 多页支持。GeneralBasicOCR + IsPdf 每次仅识别一页，
                # 这里按 _pdf_page_count 探测的页数循环调用，逐页合并 text + pages。
                total_pages = pc if (pc and pc > 0) else 1
                merged_pages: list[dict[str, object]] = []
                merged_text_parts: list[str] = []
                last_outcome = None
                last_err_code = ""
                last_err_reason = ""
                last_err_hint = ""
                duration_acc = 0.0
                for page_no in range(1, total_pages + 1):
                    page_out = run_tencent_ocr(
                        path,
                        secret_id=settings.v16_tencent_secret_id,
                        secret_key=settings.v16_tencent_secret_key,
                        region=settings.v16_tencent_region,
                        timeout_sec=float(settings.v16_ocr_timeout_sec or 60.0),
                        is_pdf=True,
                        pdf_page_number=page_no,
                    )
                    duration_acc += float(page_out.duration_ms or 0.0)
                    last_outcome = page_out
                    if page_out.ok:
                        if page_out.text:
                            merged_text_parts.append(page_out.text)
                        if page_out.pages:
                            for p in page_out.pages:
                                p["page"] = page_no
                                merged_pages.append(p)
                        else:
                            merged_pages.append({"page": page_no, "text": page_out.text or ""})
                    else:
                        # 单页失败时记录最后一次错误码；如所有页都失败则下方走失败分支。
                        last_err_code = page_out.error_code or ocr_errors.OCR_PROVIDER_ERROR
                        last_err_reason = page_out.failure_reason or "腾讯云 OCR 单页失败"
                        last_err_hint = page_out.next_action_hint or ""
                if merged_text_parts:
                    out = OcrProviderOutcome(
                        ok=True,
                        text="\n\n".join(merged_text_parts).strip(),
                        pages=merged_pages,
                        provider_type=(last_outcome.provider_type if last_outcome else "tencent"),
                        production_ready=True,
                        external_processing=True,
                        duration_ms=duration_acc,
                    )
                else:
                    out = OcrProviderOutcome(
                        ok=False,
                        text="",
                        pages=merged_pages,
                        error_code=last_err_code or ocr_errors.OCR_EMPTY_RESULT,
                        failure_reason=last_err_reason or "扫描 PDF 各页 OCR 均无文本",
                        next_action_hint=last_err_hint or "检查 PDF 是否为图像扫描页 / 调整页数上限",
                        provider_type=(last_outcome.provider_type if last_outcome else "tencent"),
                        production_ready=True,
                        external_processing=True,
                        duration_ms=duration_acc,
                    )
            else:
                out = run_tencent_ocr(
                    path,
                    secret_id=settings.v16_tencent_secret_id,
                    secret_key=settings.v16_tencent_secret_key,
                    region=settings.v16_tencent_region,
                    timeout_sec=float(settings.v16_ocr_timeout_sec or 60.0),
                )
            if _local_tesseract_fallback_allowed(path, out):
                fallback_out = run_local_tesseract(path)
                if fallback_out.ok:
                    fallback_provider = "local_tesseract"
                    fallback_warning = (
                        f"primary_ocr_failed:{out.error_code or 'unknown'} -> local_tesseract"
                    )
                    out = fallback_out
        else:
            ep = (settings.v16_ocr_endpoint or "").strip()
            if not ep:
                return _failed(
                    task_id,
                    error_code=ocr_errors.OCR_NOT_CONFIGURED,
                    failure_reason="generic_http / remote 需要配置 V16_OCR_ENDPOINT",
                    next_action_hint="设置 V16_OCR_ENDPOINT",
                    duration_ms=(time.perf_counter() - t0) * 1000.0,
                )
            out = run_generic_http_ocr(
                path,
                endpoint=ep,
                api_key=settings.v16_ocr_api_key or "",
                timeout_sec=float(settings.v16_ocr_timeout_sec or 60.0),
            )
    elif provider == "local_tesseract":
        out = run_local_tesseract(path)
    elif provider in _FIXTURE_PROVIDERS:
        out = run_fixture_ocr(path)
    else:
        return _failed(
            task_id,
            error_code=ocr_errors.OCR_NOT_CONFIGURED,
            failure_reason=f"不支持的 OCR provider: {provider}",
            next_action_hint="使用 generic_http、local_tesseract、mock 或 fake",
            duration_ms=(time.perf_counter() - t0) * 1000.0,
        )

    elapsed = (time.perf_counter() - t0) * 1000.0
    duration_ms = max(elapsed, out.duration_ms)

    if not out.ok:
        task_job_store.mark_task_failed(task_id, error_code=out.error_code, failure_reason=out.failure_reason)
        return DocumentToolResult(
            tool_name="ocr_document",
            source_type="ocr_document",
            task_id=task_id,
            status="failed",
            error_code=out.error_code,
            failure_reason=out.failure_reason,
            next_action_hint=out.next_action_hint,
            duration_ms=duration_ms,
            metadata={
                "source_type": "ocr_document",
                "file_path": str(path),
                "provider": provider,
                "provider_type": out.provider_type,
                "production_ready": out.production_ready,
                "external_processing": out.external_processing,
                "estimated_cost": estimated_cost,
                "pages": [],
            },
            quality={"quality_level": "failed", "text_length": 0},
            trace=[f"v16:ocr provider={provider} err={out.error_code}"],
        )

    task_job_store.mark_task_succeeded(
        task_id,
        result_summary={"status": "success", "text_length": len(out.text)},
        result_source_id=str(path),
    )
    md = {
        "source_type": "ocr_document",
        "file_path": str(path),
        "provider": provider,
        "primary_provider": provider,
        "fallback_provider": fallback_provider,
        "fallback_used": bool(fallback_provider),
        "provider_type": out.provider_type,
        "production_ready": out.production_ready,
        "external_processing": out.external_processing,
        "estimated_cost": estimated_cost,
        "cost_used": estimated_cost,
        "pages": out.pages,
        "page_count": len(out.pages) if out.pages else 1,
        "quality_degraded": bool(fallback_provider),
    }
    return DocumentToolResult(
        tool_name="ocr_document",
        source_type="ocr_document",
        task_id=task_id,
        status="success",
        text=out.text,
        structured_data={"pages": out.pages, "page_count": len(out.pages) if out.pages else 1},
        metadata=md,
        quality={"quality_level": "usable", "text_length": len(out.text)},
        warnings=[fallback_warning] if fallback_warning else [],
        duration_ms=duration_ms,
        trace=[
            (
                f"v16:ocr success provider={provider} fallback={fallback_provider or 'none'} "
                f"type={out.provider_type} len={len(out.text)}"
            )
        ],
    )


register(
    OcrToolSchema(
        tool_name="ocr_document",
        description="OCR document tool with generic HTTP / local Tesseract / fixture providers.",
        input_schema={"type": "object", "required": ["file_path"], "properties": {"file_path": {"type": "string"}}},
        output_schema={"type": "object", "properties": {"status": {"type": "string"}, "text": {"type": "string"}}},
        call_fn=_ocr_document,
        enabled=True,
    )
)
