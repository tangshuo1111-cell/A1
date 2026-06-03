from __future__ import annotations

from pathlib import Path

from config.settings import settings
from tools.asr import registry as asr_registry


class AsrAdapterResult:
    def __init__(
        self,
        *,
        available: bool,
        text: str = "",
        error: str = "",
        provider: str = "",
        model: str = "",
        provider_chain: list[str] | None = None,
        provider_failures: list[dict[str, str]] | None = None,
        provider_attempts: list[dict[str, object]] | None = None,
    ) -> None:
        self.available = available
        self.text = text
        self.error = error
        self.provider = provider
        self.model = model
        self.provider_chain = list(provider_chain or [])
        self.provider_failures = list(provider_failures or [])
        self.provider_attempts = list(provider_attempts or [])


def resolve_video_asr_provider_chain(*, source_type: str) -> tuple[str, ...]:
    raw = settings.v16_web_video_asr_provider_chain if source_type == "web_video" else settings.v16_local_video_asr_provider_chain
    parts = [p.strip().lower() for p in str(raw or "").split(",") if p.strip()]
    if not parts:
        base = (getattr(settings, "v16_asr_provider", None) or settings.asr_provider or "siliconflow").strip().lower()
        return (base,) if base else ("siliconflow",)
    return tuple(parts)


def call_sync_asr(audio_path: Path, *, duration_sec: float, session_id: str) -> AsrAdapterResult:
    result = asr_registry.call_tool(
        "asr_transcribe",
        file_path=str(audio_path),
        duration_sec=duration_sec,
        session_id=session_id,
        user_confirmed=True,
        force_sync=True,
        provider_chain=resolve_video_asr_provider_chain(source_type="local_video"),
        deadline_ms=int(getattr(settings, "v16_video_sync_deadline_ms", 20000) or 20000),
    )
    if result.status == "success" and (result.text or "").strip():
        meta = dict(result.metadata or {})
        return AsrAdapterResult(
            available=True,
            text=(result.text or "").strip(),
            provider=str(meta.get("provider") or ""),
            model=str(meta.get("provider_type") or ""),
            provider_chain=list(meta.get("provider_chain") or []),
            provider_failures=list(meta.get("provider_failures") or []),
            provider_attempts=list(meta.get("provider_attempts") or []),
        )
    meta = dict(result.metadata or {})
    return AsrAdapterResult(
        available=False,
        error=result.failure_reason or result.error_code or "asr_failed",
        provider=str(meta.get("provider") or ""),
        model=str(meta.get("provider_type") or ""),
        provider_chain=list(meta.get("provider_chain") or []),
        provider_failures=list(meta.get("provider_failures") or []),
        provider_attempts=list(meta.get("provider_attempts") or []),
    )
