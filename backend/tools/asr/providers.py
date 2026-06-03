"""
V16 R4-C：ASR provider（generic HTTP multipart + 可选本地 whisper / faster-whisper）。
"""

from __future__ import annotations

import base64
import json
import logging
import mimetypes
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx

from tools.asr import errors as asr_errors
from tools.asr.response_parse import (
    parse_http_asr_json,
    parse_tencent_asr_json,
    parse_tencent_flash_asr_json,
)
from tools.asr.tencent_sig import (
    TENCENT_ASR_ACTION,
    TENCENT_ASR_HOST,
    TENCENT_ASR_VERSION,
    TENCENT_FLASH_ASR_HOST,
    tencent_flash_signature,
    tencent_tc3_headers,
)

logger = logging.getLogger("light_maqa")


@dataclass
class AsrProviderOutcome:
    ok: bool
    text: str = ""
    segments: list[dict[str, Any]] = field(default_factory=list)
    error_code: str = ""
    failure_reason: str = ""
    next_action_hint: str = ""
    provider_type: str = ""
    production_ready: bool = False
    external_processing: bool = False
    duration_ms: float = 0.0
    http_status: int = 0
    response_snippet: str = ""


def _guess_mime(path: Path) -> str:
    mime, _ = mimetypes.guess_type(str(path))
    return mime or "application/octet-stream"


def _voice_format(path: Path) -> str:
    ext = path.suffix.lower().lstrip(".")
    if ext in {"mp3", "wav", "m4a", "aac", "mp4", "pcm", "ogg", "flac"}:
        return ext
    return "mp3"


def run_generic_http_asr(
    file_path: Path,
    *,
    endpoint: str,
    api_key: str,
    timeout_sec: float,
) -> AsrProviderOutcome:
    ep = (endpoint or "").strip()
    if not ep:
        return AsrProviderOutcome(
            ok=False,
            error_code=asr_errors.ASR_NOT_CONFIGURED,
            failure_reason="未配置 V16_ASR_ENDPOINT",
            next_action_hint="设置 V16_ASR_ENDPOINT",
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
        logger.warning("asr generic_http http: %s", e)
        return AsrProviderOutcome(
            ok=False,
            error_code=asr_errors.ASR_PROVIDER_ERROR,
            failure_reason=f"ASR API HTTP 错误: {e.response.status_code}",
            next_action_hint="检查 endpoint 与鉴权",
            provider_type="generic_http",
            production_ready=True,
            external_processing=True,
            duration_ms=(time.perf_counter() - t0) * 1000.0,
        )
    except (OSError, ValueError, RuntimeError, TimeoutError) as e:
        logger.warning("asr generic_http request: %s", e)
        return AsrProviderOutcome(
            ok=False,
            error_code=asr_errors.ASR_PROVIDER_ERROR,
            failure_reason=f"ASR 请求失败: {e}",
            next_action_hint="检查网络与 V16_ASR_TIMEOUT_SEC",
            provider_type="generic_http",
            production_ready=True,
            external_processing=True,
            duration_ms=(time.perf_counter() - t0) * 1000.0,
        )
    try:
        data = resp.json()
    except json.JSONDecodeError:
        return AsrProviderOutcome(
            ok=False,
            error_code=asr_errors.ASR_INVALID_RESPONSE,
            failure_reason="ASR API 返回非 JSON",
            next_action_hint="确认远端返回 JSON（text / segments）",
            provider_type="generic_http",
            production_ready=True,
            external_processing=True,
            duration_ms=(time.perf_counter() - t0) * 1000.0,
        )
    text, segments, err = parse_http_asr_json(data)
    elapsed = (time.perf_counter() - t0) * 1000.0
    if err:
        return AsrProviderOutcome(
            ok=False,
            text=text,
            segments=segments,
            error_code=err,
            failure_reason=(
                "ASR 返回无有效文本"
                if err == asr_errors.ASR_EMPTY_RESULT
                else "ASR 响应无法解析"
            ),
            next_action_hint="检查 ASR 服务返回字段",
            provider_type="generic_http",
            production_ready=True,
            external_processing=True,
            duration_ms=elapsed,
        )
    return AsrProviderOutcome(
        ok=True,
        text=text,
        segments=segments,
        provider_type="generic_http",
        production_ready=True,
        external_processing=True,
        duration_ms=elapsed,
    )


def run_tencent_asr(
    file_path: Path,
    *,
    secret_id: str,
    secret_key: str,
    region: str,
    engine_model_type: str,
    timeout_sec: float,
) -> AsrProviderOutcome:
    sid = (secret_id or "").strip()
    skey = (secret_key or "").strip()
    if not sid or not skey:
        return AsrProviderOutcome(
            ok=False,
            error_code=asr_errors.ASR_NOT_CONFIGURED,
            failure_reason="未配置 V16_TENCENT_SECRET_ID / V16_TENCENT_SECRET_KEY",
            next_action_hint="从环境变量设置腾讯云 SecretId / SecretKey",
            provider_type="tencent",
            production_ready=True,
            external_processing=True,
        )
    t0 = time.perf_counter()
    payload = json.dumps(
        {
            "EngSerViceType": (engine_model_type or "16k_zh").strip() or "16k_zh",
            "SourceType": 1,
            "VoiceFormat": _voice_format(file_path),
            "Data": base64.b64encode(file_path.read_bytes()).decode("ascii"),
        },
        separators=(",", ":"),
    )
    ts = int(time.time())
    headers = tencent_tc3_headers(
        secret_id=sid,
        secret_key=skey,
        service="asr",
        host=TENCENT_ASR_HOST,
        action=TENCENT_ASR_ACTION,
        version=TENCENT_ASR_VERSION,
        region=(region or "ap-guangzhou").strip() or "ap-guangzhou",
        payload=payload,
        timestamp=ts,
    )
    try:
        with httpx.Client(timeout=timeout_sec) as client:
            resp = client.post(f"https://{TENCENT_ASR_HOST}", headers=headers, content=payload)
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPStatusError as e:
        return AsrProviderOutcome(
            ok=False,
            error_code=asr_errors.ASR_PROVIDER_ERROR,
            failure_reason=f"腾讯云 ASR HTTP 错误: {e.response.status_code}",
            next_action_hint="检查腾讯云 ASR 开通状态、音频格式、地域与鉴权",
            provider_type="tencent",
            production_ready=True,
            external_processing=True,
            duration_ms=(time.perf_counter() - t0) * 1000.0,
        )
    except (OSError, ValueError, RuntimeError, TimeoutError) as e:
        return AsrProviderOutcome(
            ok=False,
            error_code=asr_errors.ASR_PROVIDER_ERROR,
            failure_reason=f"腾讯云 ASR 请求失败: {e}",
            next_action_hint="检查网络、密钥与 V16_ASR_TIMEOUT_SEC",
            provider_type="tencent",
            production_ready=True,
            external_processing=True,
            duration_ms=(time.perf_counter() - t0) * 1000.0,
        )
    text, segments, err, msg = parse_tencent_asr_json(data)
    elapsed = (time.perf_counter() - t0) * 1000.0
    if err:
        return AsrProviderOutcome(
            ok=False,
            text=text,
            segments=segments,
            error_code=err,
            failure_reason=msg or "腾讯云 ASR 响应无有效文本",
            next_action_hint="检查输入音频与腾讯云 SentenceRecognition API 返回",
            provider_type="tencent",
            production_ready=True,
            external_processing=True,
            duration_ms=elapsed,
        )
    return AsrProviderOutcome(
        ok=True,
        text=text,
        segments=segments,
        provider_type="tencent",
        production_ready=True,
        external_processing=True,
        duration_ms=elapsed,
    )


def run_tencent_flash_asr(
    file_path: Path,
    *,
    appid: str,
    secret_id: str,
    secret_key: str,
    engine_model_type: str,
    timeout_sec: float,
) -> AsrProviderOutcome:
    appid_clean = (appid or "").strip()
    sid = (secret_id or "").strip()
    skey = (secret_key or "").strip()
    if not appid_clean or not sid or not skey:
        return AsrProviderOutcome(
            ok=False,
            error_code=asr_errors.ASR_NOT_CONFIGURED,
            failure_reason=(
                "未配置 V16_TENCENT_APPID / V16_TENCENT_SECRET_ID / "
                "V16_TENCENT_SECRET_KEY"
            ),
            next_action_hint="从环境变量设置腾讯云 AppId / SecretId / SecretKey",
            provider_type="tencent_flash",
            production_ready=True,
            external_processing=True,
        )

    content = file_path.read_bytes()
    t0 = time.perf_counter()
    params = {
        "engine_type": (engine_model_type or "16k_zh").strip() or "16k_zh",
        "secretid": sid,
        "timestamp": str(int(time.time())),
        "voice_format": _voice_format(file_path),
    }
    signature = tencent_flash_signature(appid=appid_clean, secret_key=skey, params=params)
    url = f"https://{TENCENT_FLASH_ASR_HOST}/asr/flash/v1/{appid_clean}?{urlencode(params)}"
    try:
        with httpx.Client(timeout=timeout_sec) as client:
            resp = client.post(
                url,
                headers={
                    "Authorization": signature,
                    "Content-Type": "application/octet-stream",
                    "Host": TENCENT_FLASH_ASR_HOST,
                },
                content=content,
            )
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPStatusError as e:
        snippet = (e.response.text or "").strip().replace("\r", " ").replace("\n", " ")[:240]
        return AsrProviderOutcome(
            ok=False,
            error_code=asr_errors.ASR_PROVIDER_ERROR,
            failure_reason=(
                f"腾讯云 Flash ASR HTTP 错误: {e.response.status_code}"
                + (f" response={snippet}" if snippet else "")
            ),
            next_action_hint=(
                "检查腾讯云 Flash ASR 接口是否已开通、AppId 是否对应 ASR 资源、"
                "以及当前域名/路径是否与该账号支持的 Flash ASR 产品形态匹配。"
            ),
            provider_type="tencent_flash",
            production_ready=True,
            external_processing=True,
            duration_ms=(time.perf_counter() - t0) * 1000.0,
            http_status=int(e.response.status_code or 0),
            response_snippet=snippet,
        )
    except (OSError, ValueError, RuntimeError, TimeoutError) as e:
        return AsrProviderOutcome(
            ok=False,
            error_code=asr_errors.ASR_PROVIDER_ERROR,
            failure_reason=f"腾讯云 Flash ASR 请求失败: {e}",
            next_action_hint="检查网络、密钥、AppId 与 V16_ASR_TIMEOUT_SEC",
            provider_type="tencent_flash",
            production_ready=True,
            external_processing=True,
            duration_ms=(time.perf_counter() - t0) * 1000.0,
        )

    text, segments, err, msg = parse_tencent_flash_asr_json(data)
    elapsed = (time.perf_counter() - t0) * 1000.0
    if err:
        return AsrProviderOutcome(
            ok=False,
            text=text,
            segments=segments,
            error_code=err,
            failure_reason=msg or "腾讯云 Flash ASR 响应无有效文本",
            next_action_hint="检查输入音频与腾讯云 Flash ASR API 返回",
            provider_type="tencent_flash",
            production_ready=True,
            external_processing=True,
            duration_ms=elapsed,
        )
    return AsrProviderOutcome(
        ok=True,
        text=text,
        segments=segments,
        provider_type="tencent_flash",
        production_ready=True,
        external_processing=True,
        duration_ms=elapsed,
    )


def run_dashscope_asr(
    file_path: Path,
    *,
    api_key: str,
    model: str,
    timeout_sec: float,
) -> AsrProviderOutcome:
    key = (api_key or "").strip()
    model_name = (model or "").strip() or "paraformer-v2"
    if not key:
        return AsrProviderOutcome(
            ok=False,
            error_code=asr_errors.ASR_NOT_CONFIGURED,
            failure_reason="未配置 DASHSCOPE_API_KEY",
            next_action_hint="在环境变量或 .env 中设置 DASHSCOPE_API_KEY",
            provider_type="dashscope",
            production_ready=True,
            external_processing=True,
        )
    t0 = time.perf_counter()
    try:
        import dashscope  # type: ignore[import-untyped]
    except ImportError:
        return AsrProviderOutcome(
            ok=False,
            error_code=asr_errors.ASR_DEPENDENCY_MISSING,
            failure_reason="未安装 dashscope SDK",
            next_action_hint="py -3.12 -m pip install -U dashscope",
            provider_type="dashscope",
            production_ready=True,
            external_processing=True,
            duration_ms=(time.perf_counter() - t0) * 1000.0,
        )

    try:
        upload = dashscope.Files.upload(str(file_path), purpose="inference", api_key=key)
        if int(getattr(upload, "status_code", 0) or 0) != 200:
            return AsrProviderOutcome(
                ok=False,
                error_code=asr_errors.ASR_PROVIDER_ERROR,
                failure_reason=f"DashScope 上传失败: {getattr(upload, 'message', '') or getattr(upload, 'code', '')}",
                next_action_hint="检查 DASHSCOPE_API_KEY、文件格式与网络",
                provider_type="dashscope",
                production_ready=True,
                external_processing=True,
                duration_ms=(time.perf_counter() - t0) * 1000.0,
            )
        uploaded = ((getattr(upload, "output", None) or {}).get("uploaded_files") or [{}])[0]
        file_id = str(uploaded.get("file_id") or "").strip()
        if not file_id:
            return AsrProviderOutcome(
                ok=False,
                error_code=asr_errors.ASR_INVALID_RESPONSE,
                failure_reason="DashScope 上传返回缺少 file_id",
                next_action_hint="检查 DashScope Files.upload 返回结构",
                provider_type="dashscope",
                production_ready=True,
                external_processing=True,
                duration_ms=(time.perf_counter() - t0) * 1000.0,
            )
        file_meta = dashscope.Files.get(file_id, api_key=key)
        file_url = str(((getattr(file_meta, "output", None) or {}).get("url")) or "").strip()
        if not file_url:
            return AsrProviderOutcome(
                ok=False,
                error_code=asr_errors.ASR_INVALID_RESPONSE,
                failure_reason="DashScope 文件元数据缺少 url",
                next_action_hint="检查 DashScope Files.get 返回结构",
                provider_type="dashscope",
                production_ready=True,
                external_processing=True,
                duration_ms=(time.perf_counter() - t0) * 1000.0,
            )

        response = dashscope.Transcription.call(
            model=model_name,
            file_urls=[file_url],
            api_key=key,
            disfluency_removal_enabled=False,
            diarization_enabled=False,
            timestamp_alignment_enabled=False,
        )
        if int(getattr(response, "status_code", 0) or 0) != 200:
            return AsrProviderOutcome(
                ok=False,
                error_code=asr_errors.ASR_PROVIDER_ERROR,
                failure_reason=f"DashScope 转写提交失败: {getattr(response, 'message', '') or getattr(response, 'code', '')}",
                next_action_hint="检查模型名、上传 URL 与 DashScope 状态",
                provider_type="dashscope",
                production_ready=True,
                external_processing=True,
                duration_ms=(time.perf_counter() - t0) * 1000.0,
            )
        output = getattr(response, "output", None) or {}
        results = output.get("results") or []
        succeeded = next(
            (
                item
                for item in results
                if str(item.get("subtask_status") or "").upper() == "SUCCEEDED"
                and item.get("transcription_url")
            ),
            None,
        )
        if not succeeded:
            failure = results[0] if results else {}
            code = str(failure.get("code") or output.get("code") or asr_errors.ASR_EMPTY_RESULT)
            message = str(failure.get("message") or output.get("message") or "DashScope 未返回有效语音片段")
            return AsrProviderOutcome(
                ok=False,
                error_code=code,
                failure_reason=message,
                next_action_hint="检查音频内容、模型与上传文件可访问性",
                provider_type="dashscope",
                production_ready=True,
                external_processing=True,
                duration_ms=(time.perf_counter() - t0) * 1000.0,
            )
        transcription_url = str(succeeded.get("transcription_url") or "").strip()
        if not transcription_url:
            return AsrProviderOutcome(
                ok=False,
                error_code=asr_errors.ASR_INVALID_RESPONSE,
                failure_reason="DashScope 结果缺少 transcription_url",
                next_action_hint="检查 DashScope 结果结构",
                provider_type="dashscope",
                production_ready=True,
                external_processing=True,
                duration_ms=(time.perf_counter() - t0) * 1000.0,
            )
        with httpx.Client(timeout=timeout_sec, follow_redirects=True) as client:
            result_resp = client.get(transcription_url)
        result_resp.raise_for_status()
        result_data = result_resp.json()
    except httpx.HTTPStatusError as e:
        snippet = (e.response.text or "").strip().replace("\r", " ").replace("\n", " ")[:240]
        return AsrProviderOutcome(
            ok=False,
            error_code=asr_errors.ASR_PROVIDER_ERROR,
            failure_reason=f"DashScope 结果下载失败: {e.response.status_code}" + (f" response={snippet}" if snippet else ""),
            next_action_hint="检查 transcription_url 可访问性与时效",
            provider_type="dashscope",
            production_ready=True,
            external_processing=True,
            duration_ms=(time.perf_counter() - t0) * 1000.0,
            http_status=int(e.response.status_code or 0),
            response_snippet=snippet,
        )
    except Exception as e:  # noqa: BLE001
        return AsrProviderOutcome(
            ok=False,
            error_code=asr_errors.ASR_PROVIDER_ERROR,
            failure_reason=f"DashScope ASR 请求失败: {type(e).__name__}: {e}",
            next_action_hint="检查 DASHSCOPE_API_KEY、模型名、文件上传与网络",
            provider_type="dashscope",
            production_ready=True,
            external_processing=True,
            duration_ms=(time.perf_counter() - t0) * 1000.0,
        )

    transcripts = result_data.get("transcripts") or []
    text_parts: list[str] = []
    segments: list[dict[str, Any]] = []
    for transcript in transcripts:
        text = str(transcript.get("text") or "").strip()
        if text:
            text_parts.append(text)
        for sentence in transcript.get("sentences") or []:
            sent_text = str(sentence.get("text") or "").strip()
            if not sent_text:
                continue
            segments.append(
                {
                    "start_time": float(sentence.get("begin_time", 0.0)) / 1000.0,
                    "end_time": float(sentence.get("end_time", 0.0)) / 1000.0,
                    "text": sent_text,
                }
            )
    final_text = "\n".join(part for part in text_parts if part).strip()
    elapsed = (time.perf_counter() - t0) * 1000.0
    if not final_text:
        return AsrProviderOutcome(
            ok=False,
            error_code=asr_errors.ASR_EMPTY_RESULT,
            failure_reason="DashScope 返回空文本",
            next_action_hint="检查音频内容或切换模型",
            provider_type="dashscope",
            production_ready=True,
            external_processing=True,
            duration_ms=elapsed,
        )
    return AsrProviderOutcome(
        ok=True,
        text=final_text,
        segments=segments,
        provider_type="dashscope",
        production_ready=True,
        external_processing=True,
        duration_ms=elapsed,
    )


def run_fixture_asr(file_path: Path) -> AsrProviderOutcome:
    p = file_path if isinstance(file_path, Path) else Path(file_path)
    text = f"ASR fixture transcript for {p.name}"
    return AsrProviderOutcome(
        ok=True,
        text=text,
        segments=[{"start_time": 0.0, "end_time": 1.0, "text": text}],
        provider_type="fixture",
        production_ready=False,
        external_processing=False,
    )


def run_local_faster_whisper(file_path: Path, *, model_size: str) -> AsrProviderOutcome:
    t0 = time.perf_counter()
    try:
        from faster_whisper import WhisperModel  # type: ignore[import-untyped]
    except ImportError:
        return AsrProviderOutcome(
            ok=False,
            error_code=asr_errors.ASR_DEPENDENCY_MISSING,
            failure_reason="未安装 faster_whisper",
            next_action_hint="pip install faster-whisper",
            provider_type="faster_whisper",
            production_ready=True,
            external_processing=False,
            duration_ms=(time.perf_counter() - t0) * 1000.0,
        )
    ms = (model_size or "").strip() or "tiny"
    try:
        model = WhisperModel(ms, device="cpu", compute_type="int8")
    except (OSError, ValueError, RuntimeError, TimeoutError) as e:
        return AsrProviderOutcome(
            ok=False,
            error_code=asr_errors.ASR_MODEL_MISSING,
            failure_reason=f"无法加载 faster-whisper 模型: {e}",
            next_action_hint="检查 V16_ASR_MODEL 与模型缓存",
            provider_type="faster_whisper",
            production_ready=True,
            external_processing=False,
            duration_ms=(time.perf_counter() - t0) * 1000.0,
        )
    try:
        segs_out: list[dict[str, Any]] = []
        parts: list[str] = []
        segments, _info = model.transcribe(str(file_path), beam_size=1)
        for seg in segments:
            t = (seg.text or "").strip()
            if not t:
                continue
            segs_out.append({"start_time": float(seg.start), "end_time": float(seg.end), "text": t})
            parts.append(t)
        text = "\n".join(parts).strip()
    except (OSError, ValueError, RuntimeError, TimeoutError) as e:
        return AsrProviderOutcome(
            ok=False,
            error_code=asr_errors.ASR_PROVIDER_ERROR,
            failure_reason=f"faster-whisper 转写失败: {e}",
            provider_type="faster_whisper",
            production_ready=True,
            external_processing=False,
            duration_ms=(time.perf_counter() - t0) * 1000.0,
        )
    elapsed = (time.perf_counter() - t0) * 1000.0
    if not text:
        return AsrProviderOutcome(
            ok=False,
            error_code=asr_errors.ASR_EMPTY_RESULT,
            failure_reason="faster-whisper 返回空文本",
            provider_type="faster_whisper",
            production_ready=True,
            external_processing=False,
            duration_ms=elapsed,
        )
    return AsrProviderOutcome(
        ok=True,
        text=text,
        segments=segs_out,
        provider_type="faster_whisper",
        production_ready=True,
        external_processing=False,
        duration_ms=elapsed,
    )


def run_local_whisper(file_path: Path, *, model_name: str) -> AsrProviderOutcome:
    t0 = time.perf_counter()
    try:
        import whisper  # type: ignore[import-untyped]
    except ImportError:
        return AsrProviderOutcome(
            ok=False,
            error_code=asr_errors.ASR_DEPENDENCY_MISSING,
            failure_reason="未安装 openai-whisper",
            next_action_hint="pip install openai-whisper",
            provider_type="local_whisper",
            production_ready=True,
            external_processing=False,
            duration_ms=(time.perf_counter() - t0) * 1000.0,
        )
    mn = (model_name or "").strip() or "tiny"
    try:
        wmodel = whisper.load_model(mn)
    except (OSError, ValueError, RuntimeError, TimeoutError) as e:
        return AsrProviderOutcome(
            ok=False,
            error_code=asr_errors.ASR_MODEL_MISSING,
            failure_reason=f"无法加载 whisper 模型: {e}",
            next_action_hint="检查模型名与下载",
            provider_type="local_whisper",
            production_ready=True,
            external_processing=False,
            duration_ms=(time.perf_counter() - t0) * 1000.0,
        )
    try:
        result = wmodel.transcribe(str(file_path))
    except (OSError, ValueError, RuntimeError, TimeoutError) as e:
        return AsrProviderOutcome(
            ok=False,
            error_code=asr_errors.ASR_PROVIDER_ERROR,
            failure_reason=f"whisper 转写失败: {e}",
            provider_type="local_whisper",
            production_ready=True,
            external_processing=False,
            duration_ms=(time.perf_counter() - t0) * 1000.0,
        )
    segs_raw = result.get("segments") or []
    segs: list[dict[str, Any]] = []
    for s in segs_raw:
        if not isinstance(s, dict):
            continue
        t = str(s.get("text") or "").strip()
        if not t:
            continue
        segs.append(
            {
                "start_time": float(s.get("start", 0.0)),
                "end_time": float(s.get("end", 0.0)),
                "text": t,
            }
        )
    text = str(result.get("text") or "").strip()
    if not text and segs:
        text = "\n".join(x["text"] for x in segs)
    elapsed = (time.perf_counter() - t0) * 1000.0
    if not text:
        return AsrProviderOutcome(
            ok=False,
            error_code=asr_errors.ASR_EMPTY_RESULT,
            failure_reason="whisper 返回空文本",
            provider_type="local_whisper",
            production_ready=True,
            external_processing=False,
            duration_ms=elapsed,
        )
    return AsrProviderOutcome(
        ok=True,
        text=text,
        segments=segs,
        provider_type="local_whisper",
        production_ready=True,
        external_processing=False,
        duration_ms=elapsed,
    )
