"""
OCR provider 实现（generic HTTP multipart + 本地 Tesseract 可选路径）。
"""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import json
import logging
import mimetypes
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from tools.ocr import errors as ocr_errors

logger = logging.getLogger("light_maqa")

_TENCENT_OCR_HOST = "ocr.tencentcloudapi.com"
_TENCENT_OCR_VERSION = "2018-11-19"
_TENCENT_OCR_ACTION = "GeneralBasicOCR"


@dataclass
class OcrProviderOutcome:
    ok: bool
    text: str = ""
    pages: list[dict[str, Any]] = field(default_factory=list)
    error_code: str = ""
    failure_reason: str = ""
    next_action_hint: str = ""
    provider_type: str = ""
    production_ready: bool = False
    external_processing: bool = False
    duration_ms: float = 0.0


def _guess_mime(path: Path) -> str:
    mime, _ = mimetypes.guess_type(str(path))
    return mime or "application/octet-stream"


def _combine_pages(pages: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for p in sorted(pages, key=lambda x: int(x.get("page") or 0)):
        t = str(p.get("text") or "").strip()
        if t:
            parts.append(t)
    return "\n\n".join(parts).strip()


def _tencent_tc3_headers(
    *,
    secret_id: str,
    secret_key: str,
    service: str,
    host: str,
    action: str,
    version: str,
    region: str,
    payload: str,
    timestamp: int,
) -> dict[str, str]:
    algorithm = "TC3-HMAC-SHA256"
    date = dt.datetime.fromtimestamp(timestamp, tz=dt.UTC).strftime("%Y-%m-%d")
    canonical_headers = (
        "content-type:application/json; charset=utf-8\n"
        f"host:{host}\n"
        f"x-tc-action:{action.lower()}\n"
    )
    signed_headers = "content-type;host;x-tc-action"
    hashed_payload = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    canonical_request = "\n".join(
        ["POST", "/", "", canonical_headers, signed_headers, hashed_payload]
    )
    credential_scope = f"{date}/{service}/tc3_request"
    hashed_request = hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()
    string_to_sign = "\n".join([algorithm, str(timestamp), credential_scope, hashed_request])

    def sign(key: bytes, msg: str) -> bytes:
        return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()

    secret_date = sign(("TC3" + secret_key).encode("utf-8"), date)
    secret_service = sign(secret_date, service)
    secret_signing = sign(secret_service, "tc3_request")
    signature = hmac.new(secret_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
    authorization = (
        f"{algorithm} Credential={secret_id}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )
    return {
        "Authorization": authorization,
        "Content-Type": "application/json; charset=utf-8",
        "Host": host,
        "X-TC-Action": action,
        "X-TC-Version": version,
        "X-TC-Timestamp": str(timestamp),
        "X-TC-Region": region,
    }


def parse_http_ocr_json(data: Any) -> tuple[str, list[dict[str, Any]], str | None]:
    """
    解析 OCR HTTP JSON。
    返回 (text, pages_norm, error_code)；error_code 非空表示解析失败。
    """
    if not isinstance(data, dict):
        return "", [], ocr_errors.OCR_INVALID_RESPONSE
    text_top = str(data.get("text") or "").strip()
    pages_raw = data.get("pages")
    inner = data.get("result")
    if isinstance(inner, dict) and not text_top:
        text_top = str(inner.get("text") or "").strip()
        if not isinstance(pages_raw, list) and inner.get("pages"):
            pages_raw = inner.get("pages")
    pages_norm: list[dict[str, Any]] = []
    if isinstance(pages_raw, list):
        for i, item in enumerate(pages_raw):
            if not isinstance(item, dict):
                continue
            pn = item.get("page", i + 1)
            pt = str(item.get("text") or "").strip()
            pages_norm.append({"page": int(pn) if isinstance(pn, int) else i + 1, "text": pt})
    combined_pages = _combine_pages(pages_norm) if pages_norm else ""
    if combined_pages:
        full = combined_pages
    elif text_top:
        full = text_top
    else:
        full = ""
    if not full:
        return "", pages_norm, ocr_errors.OCR_EMPTY_RESULT
    return full, pages_norm, None


def parse_tencent_ocr_json(data: Any) -> tuple[str, list[dict[str, Any]], str | None, str]:
    if not isinstance(data, dict):
        return "", [], ocr_errors.OCR_INVALID_RESPONSE, ""
    resp = data.get("Response")
    if not isinstance(resp, dict):
        return "", [], ocr_errors.OCR_INVALID_RESPONSE, ""
    err = resp.get("Error")
    if isinstance(err, dict):
        code = str(err.get("Code") or ocr_errors.OCR_PROVIDER_ERROR)
        msg = str(err.get("Message") or "Tencent OCR provider error")
        return "", [], code, msg
    words = resp.get("TextDetections")
    pages: list[dict[str, Any]] = []
    if isinstance(words, list):
        parts = []
        for item in words:
            if not isinstance(item, dict):
                continue
            t = str(item.get("DetectedText") or "").strip()
            if t:
                parts.append(t)
        text = "\n".join(parts).strip()
        if text:
            pages.append({"page": 1, "text": text})
            return text, pages, None, ""
    return "", pages, ocr_errors.OCR_EMPTY_RESULT, "Tencent OCR returned no text"


def run_generic_http_ocr(
    file_path: Path,
    *,
    endpoint: str,
    api_key: str,
    timeout_sec: float,
) -> OcrProviderOutcome:
    ep = (endpoint or "").strip()
    if not ep:
        return OcrProviderOutcome(
            ok=False,
            error_code=ocr_errors.OCR_NOT_CONFIGURED,
            failure_reason="未配置 V16_OCR_ENDPOINT",
            next_action_hint="设置 V16_OCR_ENDPOINT",
            provider_type="generic_http",
            production_ready=True,
            external_processing=True,
        )
    content = file_path.read_bytes()
    mime = _guess_mime(file_path)
    t0 = time.perf_counter()
    headers: dict[str, str] = {}
    ak = (api_key or "").strip()
    if ak:
        headers["X-API-Key"] = ak
    try:
        with httpx.Client(timeout=timeout_sec, follow_redirects=True) as client:
            resp = client.post(
                ep,
                headers=headers,
                files={"file": (file_path.name, content, mime)},
            )
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        logger.warning("ocr generic_http http: %s", e)
        return OcrProviderOutcome(
            ok=False,
            error_code=ocr_errors.OCR_PROVIDER_ERROR,
            failure_reason=f"OCR API HTTP 错误: {e.response.status_code}",
            next_action_hint="检查 endpoint 与鉴权",
            provider_type="generic_http",
            production_ready=True,
            external_processing=True,
            duration_ms=(time.perf_counter() - t0) * 1000.0,
        )
    except (OSError, ValueError, RuntimeError, TimeoutError) as e:
        logger.warning("ocr generic_http request: %s", e)
        return OcrProviderOutcome(
            ok=False,
            error_code=ocr_errors.OCR_PROVIDER_ERROR,
            failure_reason=f"OCR 请求失败: {e}",
            next_action_hint="检查网络与 V16_OCR_TIMEOUT_SEC",
            provider_type="generic_http",
            production_ready=True,
            external_processing=True,
            duration_ms=(time.perf_counter() - t0) * 1000.0,
        )
    try:
        data = resp.json()
    except json.JSONDecodeError:
        return OcrProviderOutcome(
            ok=False,
            error_code=ocr_errors.OCR_INVALID_RESPONSE,
            failure_reason="OCR API 返回非 JSON",
            next_action_hint="确认远端返回 JSON（text / pages / result.text）",
            provider_type="generic_http",
            production_ready=True,
            external_processing=True,
            duration_ms=(time.perf_counter() - t0) * 1000.0,
        )
    text, pages, err = parse_http_ocr_json(data)
    elapsed = (time.perf_counter() - t0) * 1000.0
    if err:
        return OcrProviderOutcome(
            ok=False,
            text=text,
            pages=pages,
            error_code=err,
            failure_reason=(
                "OCR 返回无有效文本"
                if err == ocr_errors.OCR_EMPTY_RESULT
                else "OCR 响应无法解析"
            ),
            next_action_hint="检查 OCR 服务返回字段",
            provider_type="generic_http",
            production_ready=True,
            external_processing=True,
            duration_ms=elapsed,
        )
    return OcrProviderOutcome(
        ok=True,
        text=text,
        pages=pages,
        provider_type="generic_http",
        production_ready=True,
        external_processing=True,
        duration_ms=elapsed,
    )


def run_tencent_ocr(
    file_path: Path,
    *,
    secret_id: str,
    secret_key: str,
    region: str,
    timeout_sec: float,
    is_pdf: bool = False,
    pdf_page_number: int | None = None,
) -> OcrProviderOutcome:
    """V16-r5b: 调用腾讯云 OCR (GeneralBasicOCR)。

    参数：
        is_pdf: True 时在 payload 中带 IsPdf=true（PDF 输入分支；GeneralBasicOCR
            支持以 ImageBase64 + IsPdf 接收 PDF 文件，每次仅识别一页）。
        pdf_page_number: 指定 PDF 页号（1-based）；is_pdf=True 时必填。
            多页 PDF 由上层（ocr_document._ocr_document）按页循环调用。
    """
    sid = (secret_id or "").strip()
    skey = (secret_key or "").strip()
    if not sid or not skey:
        return OcrProviderOutcome(
            ok=False,
            error_code=ocr_errors.OCR_NOT_CONFIGURED,
            failure_reason="未配置 V16_TENCENT_SECRET_ID / V16_TENCENT_SECRET_KEY",
            next_action_hint="从环境变量设置腾讯云 SecretId / SecretKey",
            provider_type="tencent",
            production_ready=True,
            external_processing=True,
        )
    t0 = time.perf_counter()
    payload_obj: dict[str, Any] = {
        "ImageBase64": base64.b64encode(file_path.read_bytes()).decode("ascii")
    }
    if is_pdf:
        payload_obj["IsPdf"] = True
        if pdf_page_number is not None:
            try:
                page_int = int(pdf_page_number)
            except (TypeError, ValueError):
                page_int = 1
            payload_obj["PdfPageNumber"] = max(1, page_int)
    payload = json.dumps(payload_obj, separators=(",", ":"))
    ts = int(time.time())
    headers = _tencent_tc3_headers(
        secret_id=sid,
        secret_key=skey,
        service="ocr",
        host=_TENCENT_OCR_HOST,
        action=_TENCENT_OCR_ACTION,
        version=_TENCENT_OCR_VERSION,
        region=(region or "ap-guangzhou").strip() or "ap-guangzhou",
        payload=payload,
        timestamp=ts,
    )
    try:
        with httpx.Client(timeout=timeout_sec) as client:
            resp = client.post(f"https://{_TENCENT_OCR_HOST}", headers=headers, content=payload)
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPStatusError as e:
        return OcrProviderOutcome(
            ok=False,
            error_code=ocr_errors.OCR_PROVIDER_ERROR,
            failure_reason=f"腾讯云 OCR HTTP 错误: {e.response.status_code}",
            next_action_hint="检查腾讯云 OCR 开通状态、地域与鉴权",
            provider_type="tencent",
            production_ready=True,
            external_processing=True,
            duration_ms=(time.perf_counter() - t0) * 1000.0,
        )
    except (OSError, ValueError, RuntimeError, TimeoutError, httpx.RequestError) as e:
        return OcrProviderOutcome(
            ok=False,
            error_code=ocr_errors.OCR_PROVIDER_ERROR,
            failure_reason=f"腾讯云 OCR 请求失败: {e}",
            next_action_hint="检查网络、密钥与 V16_OCR_TIMEOUT_SEC",
            provider_type="tencent",
            production_ready=True,
            external_processing=True,
            duration_ms=(time.perf_counter() - t0) * 1000.0,
        )
    text, pages, err, msg = parse_tencent_ocr_json(data)
    elapsed = (time.perf_counter() - t0) * 1000.0
    if is_pdf and pages:
        page_no = int(payload_obj.get("PdfPageNumber") or 1)
        for p in pages:
            try:  # noqa: SIM105
                p["page"] = page_no
            except (TypeError, KeyError):
                pass
    if err:
        return OcrProviderOutcome(
            ok=False,
            text=text,
            pages=pages,
            error_code=err,
            failure_reason=msg or "腾讯云 OCR 响应无有效文本",
            next_action_hint="检查输入图片/PDF与腾讯云 OCR API 返回",
            provider_type="tencent",
            production_ready=True,
            external_processing=True,
            duration_ms=elapsed,
        )
    return OcrProviderOutcome(
        ok=True,
        text=text,
        pages=pages,
        provider_type="tencent",
        production_ready=True,
        external_processing=True,
        duration_ms=elapsed,
    )


def run_local_tesseract(file_path: Path) -> OcrProviderOutcome:
    t0 = time.perf_counter()
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        return OcrProviderOutcome(
            ok=False,
            error_code=ocr_errors.OCR_DEPENDENCY_MISSING,
            failure_reason="未安装 pytesseract 或 Pillow",
            next_action_hint="pip install pytesseract pillow，并安装 Tesseract 可执行文件",
            provider_type="local_tesseract",
            production_ready=True,
            external_processing=False,
            duration_ms=(time.perf_counter() - t0) * 1000.0,
        )
    try:
        pytesseract.get_tesseract_version()
    except OSError:
        return OcrProviderOutcome(
            ok=False,
            error_code=ocr_errors.TESSERACT_NOT_INSTALLED,
            failure_reason="未检测到 Tesseract 可执行文件",
            next_action_hint="安装 Tesseract 并确保在 PATH 中",
            provider_type="local_tesseract",
            production_ready=True,
            external_processing=False,
            duration_ms=(time.perf_counter() - t0) * 1000.0,
        )
    suf = file_path.suffix.lower()
    if suf == ".pdf":
        return OcrProviderOutcome(
            ok=False,
            error_code=ocr_errors.OCR_UNSUPPORTED_LOCAL_FORMAT,
            failure_reason="local_tesseract 当前不接 PDF，请使用 generic_http 或先转图片",
            next_action_hint="设置 V16_OCR_PROVIDER=generic_http 处理扫描 PDF",
            provider_type="local_tesseract",
            production_ready=True,
            external_processing=False,
            duration_ms=(time.perf_counter() - t0) * 1000.0,
        )
    if suf not in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif", ".webp"}:
        return OcrProviderOutcome(
            ok=False,
            error_code=ocr_errors.OCR_UNSUPPORTED_LOCAL_FORMAT,
            failure_reason=f"不支持的本地 OCR 格式: {suf}",
            next_action_hint="使用图片格式或 generic_http",
            provider_type="local_tesseract",
            production_ready=True,
            external_processing=False,
            duration_ms=(time.perf_counter() - t0) * 1000.0,
        )
    try:
        with Image.open(file_path) as img:
            raw = pytesseract.image_to_string(img)
    except (OSError, ValueError, RuntimeError) as e:
        return OcrProviderOutcome(
            ok=False,
            error_code=ocr_errors.OCR_PROVIDER_ERROR,
            failure_reason=f"Tesseract 识别失败: {e}",
            next_action_hint="检查图像是否可读",
            provider_type="local_tesseract",
            production_ready=True,
            external_processing=False,
            duration_ms=(time.perf_counter() - t0) * 1000.0,
        )
    text = (raw or "").strip()
    elapsed = (time.perf_counter() - t0) * 1000.0
    if not text:
        return OcrProviderOutcome(
            ok=False,
            error_code=ocr_errors.OCR_EMPTY_RESULT,
            failure_reason="Tesseract 返回空文本",
            next_action_hint="尝试其它图像或 generic_http",
            provider_type="local_tesseract",
            production_ready=True,
            external_processing=False,
            duration_ms=elapsed,
        )
    pages = [{"page": 1, "text": text}]
    return OcrProviderOutcome(
        ok=True,
        text=text,
        pages=pages,
        provider_type="local_tesseract",
        production_ready=True,
        external_processing=False,
        duration_ms=elapsed,
    )


def run_fixture_ocr(file_path: Path) -> OcrProviderOutcome:
    p = file_path if isinstance(file_path, Path) else Path(file_path)
    text = f"OCR fixture text for {p.name}"
    return OcrProviderOutcome(
        ok=True,
        text=text,
        pages=[{"page": 1, "text": text}],
        provider_type="fixture",
        production_ready=False,
        external_processing=False,
    )
