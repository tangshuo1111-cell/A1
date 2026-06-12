"""
云 ASR（语音转文本）兜底封装。

设计边界（与 `classify_intent_with_llm` 同类纯函数模式对齐）：
- 这是 video URL 链 **当字幕缺席时** 的兜底：先 yt-dlp 抓官方字幕；
  抓不到才把音频文件交给本模块走云 ASR。
- **复用** 现有 `LLM_API_KEY`（OpenAI 兼容协议；SiliconFlow 默认）；
  不引入新 SDK、不写自家 HTTP 客户端、不引入本地模型。
- 纯函数：`transcribe_audio(file_path, ...) -> AsrResult`
  * 不依赖 TaskInput / MainDecision；
  * 不写日志/状态/全局变量；
  * 任何失败（key 缺、provider 不识、文件不存在、超时、HTTP 失败、空文本）
    都返回 `AsrResult.unavailable(error=...)`，调用方据此走 fail_explicit。

所支持的 OpenAI 兼容 endpoint：
    POST  {base_url}/audio/transcriptions
    Auth: Bearer {api_key}
    Body: multipart/form-data，字段：
        file:  音频文件二进制
        model: ASR 模型名（如 FunAudioLLM/SenseVoiceSmall）
    Resp: { "text": "..." }
（SiliconFlow 与 OpenAI Whisper 完全一致，TeleAI/TeleSpeechASR 也走同协议。）

参考：
- SiliconFlow: https://docs.siliconflow.cn/cn/api-reference/audio/create-audio-transcriptions
  默认模型 FunAudioLLM/SenseVoiceSmall（自带标点、对普通用户免费、≤1h、≤50MB）
- OpenAI:    https://platform.openai.com/docs/api-reference/audio/createTranscription
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from config.settings import settings


@dataclass(frozen=True)
class AsrResult:
    """ASR 结果（不直接进 MainDecision，由 middle runtime 自己消费）。

    - `available=True` 且 `text` 非空 → 入库 / 入材料
    - `available=False`               → middle 走 fail_explicit
    - `provider`/`model`              → 仅供 trace（不参与判断）
    - `error`                         → 失败原因短串（只在 unavailable 时有意义）
    """

    available: bool
    text: str = ""
    provider: str = ""
    model: str = ""
    error: str = ""

    @classmethod
    def ok(cls, text: str, *, provider: str, model: str) -> AsrResult:
        return cls(available=True, text=text, provider=provider, model=model, error="")

    @classmethod
    def unavailable(cls, error: str, *, provider: str = "", model: str = "") -> AsrResult:
        return cls(
            available=False, text="", provider=provider, model=model, error=error[:120]
        )


def _ext_safe(path: Path) -> str:
    return (path.suffix or ".bin").lstrip(".").lower() or "bin"


def _mime_for_audio(ext: str) -> str:
    # OpenAI 兼容 transcription 对 MIME 要求宽松，但给个合理值有利于服务器接收
    table = {
        "mp3": "audio/mpeg",
        "wav": "audio/wav",
        "m4a": "audio/mp4",
        "mp4": "audio/mp4",
        "aac": "audio/aac",
        "ogg": "audio/ogg",
        "flac": "audio/flac",
        "opus": "audio/ogg",
        "webm": "audio/webm",
    }
    return table.get(ext, "application/octet-stream")


def _tencent_fallback_available() -> bool:
    return bool(
        (settings.v16_tencent_appid or "").strip()
        and (settings.v16_tencent_secret_id or "").strip()
        and (settings.v16_tencent_secret_key or "").strip()
    )


def _run_tencent_fallback(audio_path: Path) -> AsrResult:
    from tools.asr.providers import run_tencent_flash_asr

    outcome = run_tencent_flash_asr(
        audio_path,
        appid=settings.v16_tencent_appid,
        secret_id=settings.v16_tencent_secret_id,
        secret_key=settings.v16_tencent_secret_key,
        engine_model_type=settings.v16_tencent_asr_engine_model_type,
        timeout_sec=settings.asr_timeout_seconds,
    )
    if not outcome.ok or not (outcome.text or "").strip():
        err = outcome.failure_reason or outcome.error_code or "unknown"
        return AsrResult.unavailable(
            f"tencent_flash_failed:{err}",
            provider="tencent_flash",
            model=settings.v16_tencent_asr_engine_model_type,
        )
    return AsrResult.ok(
        outcome.text.strip(),
        provider="tencent_flash",
        model=settings.v16_tencent_asr_engine_model_type,
    )


def transcribe_audio(
    audio_path: str | Path,
    *,
    timeout_seconds: float | None = None,
    provider_override: str | None = None,
    model_override: str | None = None,
) -> AsrResult:
    """把一段本地音频文件转写为可入库纯文本（云 ASR）。

    边界（**任何**失败都不抛异常，统一走 unavailable）：
    - settings.asr_effective=False（未开启 / 缺 key / provider 不识）
    - openai 包未安装
    - 文件不存在 / 大小为 0 / 大小超出 settings.asr_max_file_mb
    - HTTP 调用失败 / 超时
    - 服务器返回 text 字段为空
    """
    p = Path(audio_path)
    provider = (provider_override or settings.asr_provider or "").strip().lower()
    model = (model_override or settings.asr_model or "").strip()

    if provider in {"tencent", "tencent_flash"}:
        if not _tencent_fallback_available():
            return AsrResult.unavailable(
                "tencent_asr_not_configured",
                provider=provider,
                model=model or settings.v16_tencent_asr_engine_model_type,
            )
        return _run_tencent_fallback(p)

    if not settings.asr_effective and not _tencent_fallback_available():
        return AsrResult.unavailable("asr_disabled_or_no_key", provider=provider, model=model)

    if not p.exists() or not p.is_file():
        return AsrResult.unavailable("audio_not_found", provider=provider, model=model)

    size_bytes = p.stat().st_size
    if size_bytes <= 0:
        return AsrResult.unavailable("audio_empty", provider=provider, model=model)

    max_bytes = max(1, int(settings.asr_max_file_mb)) * 1024 * 1024
    if size_bytes > max_bytes:
        return AsrResult.unavailable(
            f"audio_too_large:{size_bytes}>max:{max_bytes}", provider=provider, model=model
        )

    try:
        from openai import OpenAI  # type: ignore[import-untyped]
    except ImportError:
        if _tencent_fallback_available():
            return _run_tencent_fallback(p)
        return AsrResult.unavailable("openai_pkg_missing", provider=provider, model=model)

    base_url = settings.asr_effective_base_url(provider)
    # 按实际 provider 选 key：siliconflow/dashscope 用各自的 ASR key，否则回退 openai key。
    _asr_key = settings.openai_api_key
    if provider == "siliconflow":
        _asr_key = settings.v16_asr_api_key or settings.openai_api_key
    elif provider == "dashscope":
        _asr_key = settings.dashscope_api_key or settings.openai_api_key
    client = OpenAI(
        api_key=_asr_key,
        base_url=base_url,
        timeout=float(timeout_seconds) if timeout_seconds else settings.asr_timeout_seconds,
        max_retries=0,  # 转写文件较大，重试代价高，由调用方决定是否重试
    )

    ext = _ext_safe(p)
    mime = _mime_for_audio(ext)
    allow_tencent_fallback = provider in {"tencent", "tencent_flash"}

    try:
        with p.open("rb") as f:
            # OpenAI Python SDK：传 (filename, fileobj, mime) 三元组以确保 multipart 字段正确
            resp = client.audio.transcriptions.create(
                model=model,
                file=(p.name, f, mime),
            )
    except Exception as e:  # noqa: BLE001 — 任何异常都收敛成结构化 unavailable
        if allow_tencent_fallback and _tencent_fallback_available():
            fallback = _run_tencent_fallback(p)
            if fallback.available:
                return fallback
            return AsrResult.unavailable(
                f"asr_call_failed:{type(e).__name__}|fallback:{fallback.error}",
                provider=provider,
                model=model,
            )
        return AsrResult.unavailable(
            f"asr_call_failed:{type(e).__name__}", provider=provider, model=model
        )

    # OpenAI SDK 对 transcription 返回的对象同时提供 .text 属性（多版本通用）
    text = ""
    try:
        text = (getattr(resp, "text", None) or "").strip()
    except (AttributeError, TypeError):
        text = ""
    if not text and isinstance(resp, dict):  # 极少数兼容服务返回 dict
        text = str(resp.get("text") or "").strip()

    if not text:
        return AsrResult.unavailable("asr_empty_text", provider=provider, model=model)

    return AsrResult.ok(text, provider=provider, model=model)


__all__ = ["AsrResult", "transcribe_audio"]
