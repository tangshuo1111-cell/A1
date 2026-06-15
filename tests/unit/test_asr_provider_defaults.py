"""ASR provider default chain — config layer only."""

from __future__ import annotations

from config.settings import settings
from services.capabilities.video.provider_chain import resolve_video_asr_provider_chain


def test_default_video_asr_provider_chain_is_dashscope_first(monkeypatch):
    monkeypatch.delenv("V16_WEB_VIDEO_ASR_PROVIDER_CHAIN", raising=False)
    monkeypatch.delenv("V16_LOCAL_VIDEO_ASR_PROVIDER_CHAIN", raising=False)
    monkeypatch.delenv("V16_ASR_PROVIDER", raising=False)
    monkeypatch.delenv("ASR_PROVIDER", raising=False)
    monkeypatch.setattr(settings, "v16_web_video_asr_provider_chain", "dashscope,siliconflow", raising=False)
    monkeypatch.setattr(settings, "v16_local_video_asr_provider_chain", "dashscope,siliconflow", raising=False)
    monkeypatch.setattr(settings, "v16_asr_provider", "", raising=False)
    monkeypatch.setattr(settings, "asr_provider", "dashscope", raising=False)

    assert resolve_video_asr_provider_chain(source_type="web_video") == ("dashscope", "siliconflow")
    assert resolve_video_asr_provider_chain(source_type="local_video") == ("dashscope", "siliconflow")
