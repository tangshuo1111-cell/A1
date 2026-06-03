from __future__ import annotations

import json
from pathlib import Path

import pytest

SAMPLES_DIR = Path("docs/current/baselines/samples")
TRACE_NEW_DIR = Path("docs/current/baselines/trace_baseline_new")
ROUTE_TABLE = Path("docs/current/migration/route_target_table.csv")

TARGET_PATHS = {
    "video_url_summary_001": [
        "application.ingress.runtime:route_chat_request",
        "application.chat.run_chat_turn:run_agno_chat_turn_impl",
        "application.chat.fast_path_entry:run_video_fast_path",
        "services.capabilities.video.early_video_support:run_web_video_tool",
    ],
    "video_url_summary_002": [
        "application.ingress.runtime:route_chat_request",
        "application.chat.run_chat_turn:run_agno_chat_turn_impl",
        "services.capabilities.video.web_video_gather:run_early_web_video_flow",
        "services.capabilities.video.queue_dispatch:queue_web_video_asr_task",
    ],
    "local_video_summary_001": [
        "application.ingress.runtime:route_chat_request",
        "application.chat.fast_path_entry:run_video_fast_path",
        "services.capabilities.video.local_video_extract_service:run_local_video_subtitle_extract",
    ],
    "small_doc_summary_001": [
        "application.ingress.runtime:route_chat_request",
        "application.chat.fast_path_entry:run_document_fast_path",
        "services.capabilities.document.summarize_service:summarize_document",
    ],
    "large_doc_ocr_001": [
        "application.ingress.runtime:route_chat_request",
        "application.chat.run_chat_turn:run_agno_chat_turn_impl",
        "services.capabilities.document.ocr_service:run_ocr_sync",
    ],
    "web_read_001": [
        "application.ingress.runtime:route_chat_request",
        "application.chat.fast_path_entry:run_web_fast_path",
        "services.capabilities.web.web_orchestration_service:fetch_web_evidence_block",
    ],
    "kb_query_simple_001": [
        "application.ingress.runtime:route_chat_request",
        "application.chat.fast_path_entry:run_kb_fast_path",
        "services.capabilities.knowledge.kb_pipeline:fetch_kb_answer_material",
    ],
    "multi_source_complex_001": [
        "application.ingress.runtime:route_chat_request",
        "application.chat.run_chat_turn:run_agno_chat_turn_impl",
        "application.chat.complex_path_entry:run_multisource_round0_answer",
        "application.chat.delivery_gate_flow:run_delivery_gate",
        "application.chat.complex_path_entry:run_feedback_round_execution",
    ],
}

TARGET_PATH_BY_SAMPLE = {
    "video_url_summary_001": "video_fast_path",
    "video_url_summary_002": "video_complex_background_hint",
    "local_video_summary_001": "video_fast_path",
    "small_doc_summary_001": "document_fast_path",
    "large_doc_ocr_001": "document_complex_ocr",
    "web_read_001": "web_fast_path",
    "kb_query_simple_001": "kb_fast_path",
    "multi_source_complex_001": "complex_autonomy_loop",
}


def _sample_id(path: Path) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("sample_id:"):
            return line.split(":", 1)[1].strip()
    raise AssertionError(f"sample_id missing in {path}")


@pytest.mark.parametrize("sample_path", sorted(SAMPLES_DIR.glob("*.yaml")), ids=lambda p: p.stem)
def test_trace_baseline_new_matches_sample_and_target_path(sample_path: Path) -> None:
    sample_id = _sample_id(sample_path)
    trace_file = TRACE_NEW_DIR / f"{sample_id}.trace.json"
    assert trace_file.exists(), f"missing trace_baseline_new for {sample_id}"
    payload = json.loads(trace_file.read_text(encoding="utf-8"))
    assert payload["sample_id"] == sample_id
    assert payload.get("baseline_version", 0) >= 2
    assert payload.get("target_path")
    assert payload.get("call_path_snapshot")
    expected = TARGET_PATHS[sample_id]
    for step in expected:
        assert step in payload["call_path_snapshot"], f"{sample_id} missing {step}"


def test_trace_baseline_new_covers_all_route_table_samples() -> None:
    import csv

    with ROUTE_TABLE.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    sample_ids = {row["sample_id"].strip() for row in rows}
    new_ids = {p.name.replace(".trace.json", "") for p in TRACE_NEW_DIR.glob("*.trace.json")}
    assert sample_ids <= new_ids
