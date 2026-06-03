"""FetchVideoResult — 视频 URL 下载/转写的统一返回结构。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class FetchVideoResult:
    """
    URL 下载 + 字幕/ASR 转写后的统一返回结构。

    任何失败都返回 `success=False` + `error` + `stage`，
    绝不抛异常给 middle runtime。
    """

    success: bool
    text: str = ""
    title: str = ""
    source_url: str = ""
    source_basename: str = ""
    text_source: str = ""    # "subtitle" | "asr" | ""
    asr_provider: str = ""
    asr_model: str = ""
    duration_sec: float = 0.0
    error: str = ""
    stage: str = ""           # "domain" | "metadata" | "subtitle" | "audio" | "asr" | ""
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def ok_subtitle(
        cls,
        *,
        text: str,
        title: str,
        source_url: str,
        source_basename: str,
        duration_sec: float,
        extra: dict[str, Any] | None = None,
    ) -> FetchVideoResult:
        return cls(
            success=True, text=text, title=title,
            source_url=source_url, source_basename=source_basename,
            text_source="subtitle", duration_sec=duration_sec,
            extra=dict(extra or {}),
        )

    @classmethod
    def ok_asr(
        cls,
        *,
        text: str,
        title: str,
        source_url: str,
        source_basename: str,
        duration_sec: float,
        provider: str,
        model: str,
        extra: dict[str, Any] | None = None,
    ) -> FetchVideoResult:
        return cls(
            success=True, text=text, title=title,
            source_url=source_url, source_basename=source_basename,
            text_source="asr", asr_provider=provider, asr_model=model,
            duration_sec=duration_sec, extra=dict(extra or {}),
        )

    @classmethod
    def failure(
        cls,
        *,
        stage: str,
        error: str,
        source_url: str = "",
        title: str = "",
        source_basename: str = "",
        duration_sec: float = 0.0,
        extra: dict[str, Any] | None = None,
    ) -> FetchVideoResult:
        return cls(
            success=False, text="", title=title,
            source_url=source_url, source_basename=source_basename,
            duration_sec=duration_sec, error=error[:240], stage=stage,
            extra=dict(extra or {}),
        )
