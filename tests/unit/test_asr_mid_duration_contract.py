"""ASR 中段长音频契约：确认后须真实入队后台 worker，不得假 queued。"""

from __future__ import annotations

from tools.asr.asr_transcribe import _asr_transcribe


def test_confirmed_mid_duration_enqueues_background_task(
    tmp_path, monkeypatch,
) -> None:
    from config.settings import settings

    audio = tmp_path / "mid.wav"
    audio.write_bytes(b"\x00" * 64)
    monkeypatch.setattr(settings, "v16_enable_asr", True)
    monkeypatch.setattr(
        "tools.asr.asr_transcribe.create_task_record",
        lambda **_: "asr-test-mid",
    )
    enqueued: list[dict[str, object]] = []

    def _fake_enqueue(**kwargs):
        enqueued.append(kwargs)
        return "memory"

    monkeypatch.setattr(
        "services.execution.task_plane_service.enqueue_asr_mid_background_task",
        _fake_enqueue,
    )

    result = _asr_transcribe(
        str(audio),
        duration_sec=1800.0,
        user_confirmed=True,
    )

    assert result.status == "queued"
    assert result.error_code == ""
    assert result.metadata.get("async_mode") == "asr_mid_background"
    assert result.metadata.get("background_task_id") == "asr-test-mid"
    assert len(enqueued) == 1
    assert enqueued[0]["task_id"] == "asr-test-mid"
    assert enqueued[0]["file_path"] == str(audio)
