"""ASR mid-background worker marks task succeeded and stitches result."""

from __future__ import annotations

from services.capabilities.asr.asr_background_executor import run_asr_mid_background_task
from services.capabilities.video.parallel_asr_service import ParallelAsrResult


def test_run_asr_mid_background_task_succeeds(tmp_path, monkeypatch) -> None:
    audio = tmp_path / "long.wav"
    audio.write_bytes(b"\x00" * 32)
    jobs: dict[str, dict] = {}

    class _Store:
        @staticmethod
        def mark_task_running(task_id, *, stage, progress=0.0):
            jobs.setdefault(task_id, {})["stage"] = stage

        @staticmethod
        def mark_task_failed(task_id, *, error_code, failure_reason, next_action_hint=""):
            jobs[task_id] = {
                "status": "failed",
                "error_code": error_code,
            }

        @staticmethod
        def mark_task_succeeded(task_id, *, result_summary, result_source_id=""):
            jobs[task_id] = {
                "status": "success",
                "result_summary": result_summary,
            }

        @staticmethod
        def update_task_async_metadata(task_id, *, metadata):
            pass

    monkeypatch.setattr(
        "services.capabilities.asr.asr_background_executor.task_job_store",
        _Store,
    )
    monkeypatch.setattr(
        "services.capabilities.asr.asr_background_executor.run_parallel_segment_asr",
        lambda *a, **k: ParallelAsrResult(
            ok=True,
            text="hello transcript",
            provider="mock",
            model="mock",
            segments=[],
        ),
    )
    monkeypatch.setattr(
        "services.capabilities.asr.asr_background_executor.final_answer_fields_for_task",
        lambda **k: {"final_answer": "draft summary"},
    )
    stitched: list[dict[str, str]] = []
    monkeypatch.setattr(
        "services.capabilities.asr.asr_background_executor.maybe_attach_task_result",
        lambda **k: stitched.append(
            {
                "session_id": k["session_id"],
                "task_id": k["task_id"],
                "lane": k["lane"],
            }
        ),
    )

    run_asr_mid_background_task("job-1", str(audio), "sess-1")

    assert jobs["job-1"]["status"] == "success"
    assert jobs["job-1"]["result_summary"]["transcript_text"] == "hello transcript"
    assert stitched == [{"session_id": "sess-1", "task_id": "job-1", "lane": "asr"}]
