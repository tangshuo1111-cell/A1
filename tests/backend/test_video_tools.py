def test_web_video_long_confirmed_queues_background_asr(monkeypatch):
    from services.capabilities.video import web_video_extract_service as mod
    from tools.video.web_video_providers import WebVideoSubtitleOutcome
    from video.web_video_chat_context import web_video_long_asr_confirmed

    queued: list[tuple[str, str, str]] = []
    monkeypatch.setattr(mod, "create_task_record", lambda **kwargs: "web-task-1")
    monkeypatch.setattr(mod.task_job_store, "mark_task_running", lambda *a, **k: None)
    monkeypatch.setattr(mod.task_job_store, "mark_task_failed", lambda *a, **k: None)
    monkeypatch.setattr(mod, "is_supported_video_url", lambda url: True)
    monkeypatch.setattr(mod.importlib.util, "find_spec", lambda name: object())
    monkeypatch.setattr(
        mod,
        "run_ytdlp_subtitle_provider",
        lambda url, automatic_captions: WebVideoSubtitleOutcome(
            ok=False,
            error_code=mod.SUBTITLE_NOT_FOUND,
            failure_reason="未找到字幕",
            title="sample",
            duration_sec=1800.0,
            duration_ms=123.0,
        ),
    )
    monkeypatch.setattr(
        mod,
        "queue_web_video_asr_task",
        lambda *, task_id, url, session_id: queued.append((task_id, url, session_id)),
    )
    token = web_video_long_asr_confirmed.set(True)
    try:
        out = mod.run_web_video_subtitle_extract("https://example.com/video", session_id="sess-web")
    finally:
        web_video_long_asr_confirmed.reset(token)

    assert out.status == "queued"
    assert out.task_id == "web-task-1"
    assert out.metadata["background_task_id"] == "web-task-1"
    assert queued == [("web-task-1", "https://example.com/video", "sess-web")]


def test_local_video_long_confirmed_queues_background_asr(monkeypatch, tmp_path):
    from services.capabilities.video import local_video_extract_service as mod
    from tools.video.embedded_subtitle import EmbeddedSubtitleOutcome
    from video.web_video_chat_context import web_video_long_asr_confirmed

    video_path = tmp_path / "movie.mp4"
    video_path.write_bytes(b"fake")
    queued: list[tuple[str, str, str]] = []

    monkeypatch.setattr(mod, "create_task_record", lambda **kwargs: "local-task-1")
    monkeypatch.setattr(mod.task_job_store, "mark_task_running", lambda *a, **k: None)
    monkeypatch.setattr(mod.task_job_store, "mark_task_failed", lambda *a, **k: None)
    monkeypatch.setattr(
        mod,
        "extract_embedded_subtitle",
        lambda path: EmbeddedSubtitleOutcome(ok=False, error_code="embedded_subtitle_not_found", failure_reason="none"),
    )
    monkeypatch.setattr(mod, "probe_local_video_duration_sec", lambda path: 2400.0)
    monkeypatch.setattr(
        mod,
        "queue_local_video_asr_task",
        lambda *, task_id, file_path, session_id: queued.append((task_id, file_path, session_id)),
    )
    token = web_video_long_asr_confirmed.set(True)
    try:
        out = mod.run_local_video_subtitle_extract(str(video_path), session_id="sess-local")
    finally:
        web_video_long_asr_confirmed.reset(token)

    assert out.status == "queued"
    assert out.task_id == "local-task-1"
    assert out.metadata["background_task_id"] == "local-task-1"
    assert queued == [("local-task-1", str(video_path), "sess-local")]


def test_web_video_sync_asr_uses_provider_chain_fallback(monkeypatch):
    from config.settings import settings as _settings
    from services.capabilities.video import web_video_extract_service as mod
    from services.capabilities.video.parallel_asr_service import ParallelAsrResult
    from tools.video.web_video_providers import WebVideoSubtitleOutcome

    # 显式锁定 provider 链，避免依赖运行环境的 .env 默认值（CI 默认是 tencent_flash）。
    monkeypatch.setattr(_settings, "v16_web_video_asr_provider_chain", "dashscope,siliconflow")
    monkeypatch.setattr(mod, "create_task_record", lambda **kwargs: "web-task-2")
    monkeypatch.setattr(mod.task_job_store, "mark_task_running", lambda *a, **k: None)
    monkeypatch.setattr(mod.task_job_store, "mark_task_failed", lambda *a, **k: None)
    monkeypatch.setattr(mod.task_job_store, "mark_task_succeeded", lambda *a, **k: None)
    monkeypatch.setattr(mod, "is_supported_video_url", lambda url: True)
    monkeypatch.setattr(mod.importlib.util, "find_spec", lambda name: object())
    monkeypatch.setattr(
        mod,
        "run_ytdlp_subtitle_provider",
        lambda url, automatic_captions: WebVideoSubtitleOutcome(
            ok=False,
            error_code=mod.SUBTITLE_NOT_FOUND,
            failure_reason="未找到字幕",
            title="sample",
            duration_sec=10.0,
            duration_ms=200.0,
        ),
    )

    seen: dict[str, object] = {}

    monkeypatch.setattr(
        mod,
        "_download_web_video_audio",
        lambda url: (__import__("pathlib").Path("dummy.wav"), __import__("pathlib").Path("."), ""),
    )
    monkeypatch.setattr(
        mod,
        "run_parallel_segment_asr",
        lambda audio_path, *, session_id, provider_chain, deadline_ms: seen.update({
            "provider_chain": list(provider_chain),
            "deadline_ms": deadline_ms,
        }) or ParallelAsrResult(
            ok=True,
            text="来自 ASR 的文字",
            provider="siliconflow",
            model="siliconflow",
            segments=[{"start_time": 0.0, "end_time": 1.0, "text": "来自 ASR 的文字"}],
            provider_failures=[{"provider": "tencent_flash", "error": "tencent_flash_failed"}],
        ),
    )
    monkeypatch.setattr(mod, "_safe_cleanup", lambda path: None)

    out = mod.run_web_video_subtitle_extract("https://example.com/video", session_id="sess-web")
    assert out.status == "success"
    assert out.metadata["provider"] == "yt_dlp+asr"
    assert out.metadata["remaining_sync_budget_ms"] >= 0
    assert out.metadata["video_probe_elapsed_ms"] >= 0
    assert seen["provider_chain"] == ["dashscope", "siliconflow"]


def test_web_video_probe_budget_exceeded_goes_background(monkeypatch):
    from services.capabilities.video import processing_service as svc
    from services.capabilities.video import web_video_extract_service as mod
    from tools.video.web_video_providers import WebVideoSubtitleOutcome

    queued: list[tuple[str, str, str]] = []
    monkeypatch.setattr(mod, "create_task_record", lambda **kwargs: "web-task-3")
    monkeypatch.setattr(mod.task_job_store, "mark_task_running", lambda *a, **k: None)
    monkeypatch.setattr(mod.task_job_store, "mark_task_failed", lambda *a, **k: None)
    monkeypatch.setattr(mod, "is_supported_video_url", lambda url: True)
    monkeypatch.setattr(mod.importlib.util, "find_spec", lambda name: object())
    monkeypatch.setattr(
        mod,
        "run_ytdlp_subtitle_provider",
        lambda url, automatic_captions: WebVideoSubtitleOutcome(
            ok=False,
            error_code=mod.SUBTITLE_NOT_FOUND,
            failure_reason="未找到字幕",
            title="sample",
            duration_sec=5.0,
            duration_ms=7000.0,
        ),
    )
    monkeypatch.setattr(
        mod,
        "queue_web_video_asr_task",
        lambda *, task_id, url, session_id: queued.append((task_id, url, session_id)),
    )
    monkeypatch.setattr(mod.settings, "v16_video_probe_budget_ms", 100)
    monkeypatch.setattr(svc, "should_force_video_background", lambda **kwargs: (True, "probe_budget_exceeded"))
    monkeypatch.setattr(svc, "should_queue_video_background", lambda **kwargs: (False, ""))

    out = mod.run_web_video_subtitle_extract("https://example.com/video", session_id="sess-web")
    assert out.status == "queued"
    assert out.metadata["queue_reason"] == "probe_budget_exceeded"
    assert queued == [("web-task-3", "https://example.com/video", "sess-web")]


def test_web_and_local_video_tools_share_same_processing_service(monkeypatch, tmp_path):
    from services.capabilities.video import local_video_extract_service as local_mod
    from services.capabilities.video import web_video_extract_service as web_mod
    from services.capabilities.video.processing_service import (
        VideoCapabilityOutcome,
        VideoProcessingResult,
        result_to_capability_pair,
    )

    video_path = tmp_path / "same.mp4"
    video_path.write_bytes(b"fake")
    seen: list[tuple[str, str]] = []

    def fake_run_video_capability(req):
        seen.append((req.source_type, req.source_ref))
        legacy = VideoProcessingResult(
            status="success",
            source_type=req.source_type,
            source_ref=req.source_ref,
            title=req.title,
            text="统一能力层输出",
            transcript_source="subtitle_file" if req.source_type == "local_video" else "subtitle",
            subtitle_format="subtitle",
            metadata={"source_type": req.source_type},
            quality={"quality_level": "good"},
            trace=[f"shared-service:{req.source_type}"],
        )
        fact, advice = result_to_capability_pair(legacy)
        return VideoCapabilityOutcome(fact=fact, advice=advice, result=legacy)

    monkeypatch.setattr(web_mod, "run_video_capability", fake_run_video_capability)
    monkeypatch.setattr(local_mod, "run_video_capability", fake_run_video_capability)

    monkeypatch.setattr(web_mod, "create_task_record", lambda **kwargs: "web-shared-1")
    monkeypatch.setattr(web_mod.task_job_store, "mark_task_running", lambda *a, **k: None)
    monkeypatch.setattr(web_mod.task_job_store, "mark_task_succeeded", lambda *a, **k: None)
    monkeypatch.setattr(web_mod, "is_supported_video_url", lambda url: True)
    monkeypatch.setattr(web_mod.importlib.util, "find_spec", lambda name: object())
    monkeypatch.setattr(
        web_mod,
        "run_ytdlp_subtitle_provider",
        lambda url, automatic_captions: type("O", (), {
            "ok": True,
            "text": "字幕文本",
            "subtitle_source": "subtitles",
            "language": "zh-CN",
            "segments": [],
            "duration_sec": 12.0,
            "duration_ms": 120.0,
            "provider": "yt_dlp",
            "provider_type": "subtitle",
            "production_ready": True,
            "error_code": "",
            "failure_reason": "",
            "next_action_hint": "",
            "metadata_extra": {},
            "title": "web title",
            "webpage_url": url,
        })(),
    )

    monkeypatch.setattr(local_mod, "create_task_record", lambda **kwargs: "local-shared-1")
    monkeypatch.setattr(local_mod.task_job_store, "mark_task_running", lambda *a, **k: None)
    monkeypatch.setattr(local_mod.task_job_store, "mark_task_succeeded", lambda *a, **k: None)
    monkeypatch.setattr(
        local_mod,
        "parse_subtitle_file",
        lambda path: ([{"start_time": 0.0, "end_time": 1.0, "text": "hi"}], "srt"),
    )
    monkeypatch.setattr(local_mod, "subtitle_segments_to_text", lambda segments: "本地字幕文本")
    subtitle_path = video_path.with_suffix(".srt")
    subtitle_path.write_text("1", encoding="utf-8")

    web_out = web_mod.run_web_video_subtitle_extract("https://example.com/video", session_id="sess-web")
    local_out = local_mod.run_local_video_subtitle_extract(str(video_path), session_id="sess-local")

    assert web_out.text == "统一能力层输出"
    assert local_out.text == "统一能力层输出"
    assert ("web_video", "https://example.com/video") in seen
    assert ("local_video", str(video_path)) in seen


def test_web_and_local_video_share_parallel_asr_service(monkeypatch, tmp_path):
    from pathlib import Path

    from services.capabilities.video import local_video_extract_service as local_mod
    from services.capabilities.video import processing_service as svc
    from services.capabilities.video import web_video_extract_service as web_mod
    from services.capabilities.video.parallel_asr_service import ParallelAsrResult
    from tools.video.embedded_subtitle import EmbeddedSubtitleOutcome
    from tools.video.web_video_providers import WebVideoSubtitleOutcome

    video_path = tmp_path / "parallel.mp4"
    video_path.write_bytes(b"fake")
    seen: list[tuple[str, tuple[str, ...]]] = []

    from config.settings import settings as _settings

    # 显式锁定 provider 链，避免依赖运行环境的 .env 默认值（CI 默认是 tencent_flash）。
    monkeypatch.setattr(_settings, "v16_web_video_asr_provider_chain", "dashscope,siliconflow")
    monkeypatch.setattr(_settings, "v16_local_video_asr_provider_chain", "dashscope,siliconflow")
    monkeypatch.setattr(web_mod, "create_task_record", lambda **kwargs: "web-par-1")
    monkeypatch.setattr(web_mod.task_job_store, "mark_task_running", lambda *a, **k: None)
    monkeypatch.setattr(web_mod.task_job_store, "mark_task_succeeded", lambda *a, **k: None)
    monkeypatch.setattr(web_mod, "is_supported_video_url", lambda url: True)
    monkeypatch.setattr(web_mod.importlib.util, "find_spec", lambda name: object())
    monkeypatch.setattr(
        web_mod,
        "run_ytdlp_subtitle_provider",
        lambda url, automatic_captions: WebVideoSubtitleOutcome(
            ok=False,
            error_code=web_mod.SUBTITLE_NOT_FOUND,
            failure_reason="未找到字幕",
            title="sample",
            duration_sec=30.0,
            duration_ms=120.0,
        ),
    )
    monkeypatch.setattr(web_mod, "_download_web_video_audio", lambda url: (Path("dummy.wav"), Path("."), ""))
    monkeypatch.setattr(web_mod, "_safe_cleanup", lambda path: None)
    monkeypatch.setattr(svc, "should_force_video_background", lambda **kwargs: (False, ""))
    monkeypatch.setattr(svc, "should_queue_video_background", lambda **kwargs: (False, ""))

    monkeypatch.setattr(local_mod, "create_task_record", lambda **kwargs: "local-par-1")
    monkeypatch.setattr(local_mod.task_job_store, "mark_task_running", lambda *a, **k: None)
    monkeypatch.setattr(local_mod.task_job_store, "mark_task_succeeded", lambda *a, **k: None)
    monkeypatch.setattr(
        local_mod,
        "extract_embedded_subtitle",
        lambda path: EmbeddedSubtitleOutcome(ok=False, error_code="embedded_subtitle_not_found", failure_reason="none"),
    )
    monkeypatch.setattr(local_mod, "probe_local_video_duration_sec", lambda path: 30.0)
    monkeypatch.setattr(local_mod, "extract_audio_wav_for_asr", lambda path: (Path("dummy.wav"), "", "", ""))

    def fake_parallel(audio_path, *, session_id, provider_chain, deadline_ms, **kwargs):
        seen.append((session_id, tuple(provider_chain)))
        return ParallelAsrResult(
            ok=True,
            text="并发 ASR 文本",
            provider="tencent_flash",
            model="tencent_flash",
            segments=[{"start_time": 0.0, "end_time": 1.0, "text": "并发 ASR 文本"}],
        )

    monkeypatch.setattr(web_mod, "run_parallel_segment_asr", fake_parallel)
    monkeypatch.setattr(local_mod, "run_parallel_segment_asr", fake_parallel)

    web_out = web_mod.run_web_video_subtitle_extract("https://example.com/video", session_id="sess-web")
    local_out = local_mod.run_local_video_subtitle_extract(str(video_path), session_id="sess-local")

    assert web_out.status == "success"
    assert local_out.status == "success"
    assert ("sess-web", ("dashscope", "siliconflow")) in seen
    assert ("sess-local", ("dashscope", "siliconflow")) in seen


def test_web_and_local_video_share_same_background_task_orchestration(monkeypatch, tmp_path):
    from services.capabilities.video import queue_dispatch as pipeline

    video_path = tmp_path / "bg.mp4"
    video_path.write_bytes(b"fake")
    seen: list[tuple[str, str, str]] = []

    monkeypatch.setattr(
        "services.capabilities.video.queue_dispatch.enqueue_video_task",
        lambda message: seen.append((message.source_type, message.source_ref, message.task_id)) or "memory",
    )
    monkeypatch.setattr(
        "services.capabilities.video.queue_dispatch.ensure_async_workers_started",
        lambda: seen.append(("worker", "started", "")),
    )

    pipeline.queue_web_video_asr_task(task_id="web-bg-1", url="https://example.com/video", session_id="sess-web")
    pipeline.queue_local_video_asr_task(task_id="local-bg-1", file_path=str(video_path), session_id="sess-local")

    assert ("web_video", "https://example.com/video", "web-bg-1") in seen
    assert ("local_video", str(video_path), "local-bg-1") in seen
    assert ("worker", "started", "") in seen


def test_parallel_segment_asr_uses_worker_pool(monkeypatch):
    from pathlib import Path

    from services.capabilities.video import parallel_asr_service as svc

    fake_seg = svc.AudioSegment(index=0, file_path=Path("dummy.wav"), start_sec=0.0, end_sec=10.0)
    monkeypatch.setattr(svc, "split_audio_for_parallel_asr", lambda *a, **k: [fake_seg])
    monkeypatch.setattr(svc, "_cleanup_segments", lambda *a, **k: None)
    monkeypatch.setattr(
        svc.asr_registry,
        "call_tool",
        lambda *a, **k: type("R", (), {"status": "success", "text": "hi", "metadata": {"provider": "tencent_flash", "provider_type": "flash"}, "structured_data": {}})(),
    )
    seen: list[tuple[int, str]] = []
    monkeypatch.setattr(
        svc,
        "run_in_video_worker_pool",
        lambda items, worker_fn, **kwargs: seen.append((len(list(items)), kwargs.get("thread_name_prefix", ""))) or [worker_fn(fake_seg)],
    )

    out = svc.run_parallel_segment_asr(
        Path("dummy.wav"),
        session_id="sess-1",
        provider_chain=("tencent_flash", "siliconflow"),
        deadline_ms=8000,
    )

    assert out.ok is True
    assert seen == [(1, "video-seg-asr")]


def test_video_segment_service_prefers_silence_points(monkeypatch):
    from services.capabilities.video import segment_service as svc

    monkeypatch.setattr(svc, "_ffprobe_duration", lambda path: 360.0)
    monkeypatch.setattr(svc, "_detect_silence_cut_points", lambda path: [118.5, 241.0])
    captured: dict[str, object] = {}

    def _fake_split(audio_path, *, cut_points, duration):
        captured["cut_points"] = list(cut_points)
        return svc.SegmentSplitResult(segments=[], mode="parallel_segments", cut_point_count=len(cut_points))

    monkeypatch.setattr(svc, "_split_audio_by_points", _fake_split)

    result = svc.split_audio_for_parallel_asr(__import__("pathlib").Path("dummy.wav"))
    assert captured["cut_points"] == [118.5, 241.0]
    assert result.cut_point_count == 2
    assert result.mode == "parallel_segments"


def test_video_segment_service_falls_back_to_hard_cut_without_silence(monkeypatch):
    from services.capabilities.video import segment_service as svc

    monkeypatch.setattr(svc, "_ffprobe_duration", lambda path: 360.0)
    monkeypatch.setattr(svc, "_detect_silence_cut_points", lambda path: [])
    captured: dict[str, object] = {}

    def _fake_split(audio_path, *, cut_points, duration):
        captured["cut_points"] = list(cut_points)
        return svc.SegmentSplitResult(segments=[], mode="parallel_segments", cut_point_count=len(cut_points))

    monkeypatch.setattr(svc, "_split_audio_by_points", _fake_split)

    result = svc.split_audio_for_parallel_asr(__import__("pathlib").Path("dummy.wav"))
    assert captured["cut_points"] == [300.0]
    assert result.cut_point_count == 1
    assert result.mode == "parallel_segments"
