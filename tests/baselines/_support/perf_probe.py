"""Run baseline samples through the new architecture path and collect perf metrics."""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import yaml
from tests._support.capability_probe_fixtures import kb_probe_sync_ok, web_probe_sync_ok

from agents.answer_agent import AnswerAgent
from agents.main_agent.schema import AgnoCollaborationPlan, MainXiezuoPan
from agents.middle_agent.schema import AgnoMaterialBundle, CailiaoPan
from application.chat.history_buffer import ChatTurnDeps
from application.chat.run_chat_turn import run_agno_chat_turn_impl
from config import feature_flags
from rag.schema import RetrievedChunk
from schemas import MainDecision

SAMPLES_DIR = Path("docs/current/baselines/samples")


@dataclass(frozen=True)
class PerfRow:
    sample_id: str
    first_response_ms: int
    total_ms: int
    llm_calls: int
    tool_calls: int
    token_in: int
    token_out: int
    success: bool
    lane: str
    mode: str


def load_samples() -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    for path in sorted(SAMPLES_DIR.glob("*.yaml")):
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        payload["_path"] = str(path)
        samples.append(payload)
    return samples


def _fast_deps() -> ChatTurnDeps:
    return ChatTurnDeps(
        histories={},
        session_prev_video={},
        session_pending_video={},
        lock=Lock(),
        main_agent=SimpleNamespace(pan=lambda *a, **k: None),
        middle_agent=SimpleNamespace(caipan=lambda *a, **k: None),
        answer_agent=SimpleNamespace(),
        run_basic_qa=lambda *a, **k: "基线探针回答。",
        path_fingerprint=lambda *a, **k: "fp",
        nodes_contract=lambda trace: {},
    )


def _document_complex_deps(message: str) -> ChatTurnDeps:
    plan = AgnoCollaborationPlan(
        decision=MainDecision(task_id="perf-doc-complex", task_status="routed"),
        force_skip_evidence=False,
        web_supplement_mode="explicit_only",
        answer_composition="default",
        xiezuo_pan=MainXiezuoPan(
            renwu_lei="wenjian",
            zhengju_need=True,
            allow_kb=False,
            allow_web=False,
            fengxian_yinzi=0.7,
            celue_tag="document_ocr",
        ),
        needs_retrieval=False,
        retrieval_strategy="none",
        answer_mode="direct",
        tools_allowed=(),
        max_rounds=1,
        original_user_intent=message,
    )
    bundle = AgnoMaterialBundle(
        knowledge_block="",
        web_block="",
        trace=["v16:document:ocr_complex"],
        knowledge_adequate=False,
        material_still_insufficient=True,
        web_judgment_reason="skip",
        kb_evidence_tier="none",
        insufficiency_signal="need_ocr",
        cailiao_pan=CailiaoPan(
            gou=False,
            kb_qiangdu=0.0,
            bukong_xinhao="que",
            laiyuan_zhu="document",
            use_kb=False,
            use_web=False,
            que_shenme="ocr",
            xia_yi_bu="bu_wang",
        ),
    )
    return ChatTurnDeps(
        histories={},
        session_prev_video={},
        session_pending_video={},
        lock=Lock(),
        main_agent=SimpleNamespace(pan=lambda *a, **k: plan),
        middle_agent=SimpleNamespace(caipan=lambda *a, **k: bundle),
        answer_agent=AnswerAgent(),
        run_basic_qa=lambda *a, **k: "大文档 OCR 复杂链首答，包含 OCR 处理说明。",
        path_fingerprint=lambda *a, **k: "fp",
        nodes_contract=lambda trace: {},
    )


def _video_local_deps(message: str) -> ChatTurnDeps:
    plan = AgnoCollaborationPlan(
        decision=MainDecision(task_id="perf-local-video", task_status="routed"),
        force_skip_evidence=False,
        web_supplement_mode="explicit_only",
        answer_composition="default",
        xiezuo_pan=MainXiezuoPan(
            renwu_lei="shipin",
            zhengju_need=True,
            allow_kb=False,
            allow_web=False,
            fengxian_yinzi=0.6,
            celue_tag="local_video",
        ),
        needs_retrieval=False,
        retrieval_strategy="none",
        answer_mode="direct",
        tools_allowed=("mcp_video_to_text",),
        max_rounds=1,
        original_user_intent=message,
    )
    bundle = AgnoMaterialBundle(
        knowledge_block="",
        web_block="",
        trace=["v16:local_video:summary"],
        knowledge_adequate=True,
        material_still_insufficient=False,
        web_judgment_reason="skip",
        kb_evidence_tier="none",
        insufficiency_signal="",
        cailiao_pan=CailiaoPan(
            gou=True,
            kb_qiangdu=0.8,
            bukong_xinhao="gou",
            laiyuan_zhu="video",
            use_kb=False,
            use_web=False,
            que_shenme="",
            xia_yi_bu="",
        ),
    )
    return ChatTurnDeps(
        histories={},
        session_prev_video={},
        session_pending_video={},
        lock=Lock(),
        main_agent=SimpleNamespace(pan=lambda *a, **k: plan),
        middle_agent=SimpleNamespace(caipan=lambda *a, **k: bundle),
        answer_agent=AnswerAgent(),
        run_basic_qa=lambda *a, **k: "本地视频总结：视频围绕基线验收与架构迁移。",
        path_fingerprint=lambda *a, **k: "fp",
        nodes_contract=lambda trace: {},
    )


def _video_long_complex_deps(message: str) -> ChatTurnDeps:
    plan = AgnoCollaborationPlan(
        decision=MainDecision(task_id="perf-long-video", task_status="routed"),
        force_skip_evidence=False,
        web_supplement_mode="explicit_only",
        answer_composition="default",
        xiezuo_pan=MainXiezuoPan(
            renwu_lei="shipin",
            zhengju_need=True,
            allow_kb=False,
            allow_web=False,
            fengxian_yinzi=0.75,
            celue_tag="long_video",
        ),
        needs_retrieval=False,
        retrieval_strategy="none",
        answer_mode="direct",
        tools_allowed=(),
        max_rounds=1,
        original_user_intent=message,
    )
    bundle = AgnoMaterialBundle(
        knowledge_block="",
        web_block="",
        trace=["v16:long_video:background_hint"],
        knowledge_adequate=False,
        material_still_insufficient=True,
        web_judgment_reason="skip",
        kb_evidence_tier="none",
        insufficiency_signal="need_asr",
        cailiao_pan=CailiaoPan(
            gou=False,
            kb_qiangdu=0.0,
            bukong_xinhao="que",
            laiyuan_zhu="video",
            use_kb=False,
            use_web=False,
            que_shenme="asr",
            xia_yi_bu="bu_wang",
        ),
    )
    return ChatTurnDeps(
        histories={},
        session_prev_video={},
        session_pending_video={},
        lock=Lock(),
        main_agent=SimpleNamespace(pan=lambda *a, **k: plan),
        middle_agent=SimpleNamespace(caipan=lambda *a, **k: bundle),
        answer_agent=AnswerAgent(),
        run_basic_qa=lambda *a, **k: "长视频已进入后台处理队列，首答包含后台提示。",
        path_fingerprint=lambda *a, **k: "fp",
        nodes_contract=lambda trace: {},
    )


def _multisource_complex_deps() -> ChatTurnDeps:
    plan = AgnoCollaborationPlan(
        decision=MainDecision(task_id="perf-multi", task_status="routed"),
        force_skip_evidence=False,
        web_supplement_mode="explicit_only",
        answer_composition="default",
        xiezuo_pan=MainXiezuoPan(
            renwu_lei="waibu",
            zhengju_need=True,
            allow_kb=True,
            allow_web=True,
            fengxian_yinzi=0.8,
            celue_tag="complex",
        ),
        job_type="multi_source_compare",
        max_rounds=2,
        needs_retrieval=True,
        retrieval_strategy="auto",
        answer_mode="knowledge_grounded",
        tools_allowed=("fetch_web",),
        original_user_intent="结合知识库、网页和文档给出建议",
        budget_policy={"llm_calls_remaining": 2, "tool_calls_remaining": 2},
    )
    bundle = AgnoMaterialBundle(
        knowledge_block="知识库资料：方案 A 成本低。",
        web_block="[Web检索] 网页资料：方案 B 落地更快。",
        trace=[],
        knowledge_adequate=False,
        material_still_insufficient=True,
        web_judgment_reason="explicit_only",
        kb_evidence_tier="partial",
        insufficiency_signal="need_compare",
        cailiao_pan=CailiaoPan(
            gou=False,
            kb_qiangdu=0.5,
            bukong_xinhao="que",
            laiyuan_zhu="mixed",
            use_kb=True,
            use_web=True,
            que_shenme="compare",
            xia_yi_bu="bu_wang",
        ),
    )
    return ChatTurnDeps(
        histories={},
        session_prev_video={},
        session_pending_video={},
        lock=Lock(),
        main_agent=SimpleNamespace(pan=lambda *a, **k: plan),
        middle_agent=SimpleNamespace(caipan=lambda *a, **k: bundle),
        answer_agent=SimpleNamespace(
            pan=lambda *_a, **_k: SimpleNamespace(lane="general", primary_path="complex_autonomy"),
            xiezuo_extra=lambda *_a, **_k: {},
            review_multisource=lambda *_a, **_k: {
                "feedback_request": {
                    "request_type": "more_web_material",
                    "reason": "需要更多证据后再签字",
                }
            },
        ),
        run_basic_qa=lambda *a, **k: "综合知识库、网页和文档后，建议优先方案 B。",
        path_fingerprint=lambda *a, **k: "fp",
        nodes_contract=lambda trace: {},
    )


def _deps_for_sample(sample_id: str, message: str) -> ChatTurnDeps:
    if sample_id == "large_doc_ocr_001":
        return _document_complex_deps(message)
    if sample_id == "local_video_summary_001":
        return _video_local_deps(message)
    if sample_id == "video_url_summary_002":
        return _video_long_complex_deps(message)
    if sample_id == "multi_source_complex_001":
        return _multisource_complex_deps()
    if sample_id == "kb_query_simple_001":
        from tests._support.fast_lane_test_plans import fast_lane_deps

        return fast_lane_deps(answer="系统默认数据库要求 PostgreSQL。")
    return _fast_deps()


def _sla_first_response_ms(sample: dict[str, Any]) -> int | None:
    for rule in sample.get("must_not_regress") or []:
        if isinstance(rule, dict) and "first_response_ms_le" in rule:
            return int(rule["first_response_ms_le"])
    return None


def sample_sla_ms(sample: dict[str, Any]) -> int | None:
    return _sla_first_response_ms(sample)


def _kb_material() -> tuple[str, list[RetrievedChunk], list[str], dict[str, Any]]:
    chunks = [
        RetrievedChunk(
            source_id="sample",
            chunk_id="sample::0",
            text="系统默认数据库要求 PostgreSQL。",
            metadata={"source_type": "document"},
            score=0.9,
            retrieval_strategy="keyword",
        ),
    ]
    material = "系统默认数据库要求 PostgreSQL。"
    caps = ["capability.kb.retrieve", "capability.kb.rerank", "capability.kb.grounding"]
    return material, chunks, caps, {"strategy_used": "keyword", "hits": 1}


@contextmanager
def perf_mocks(*, sample_id: str) -> Iterator[None]:
    patches = [
        patch(
            "application.chat.executors.fast_executor_general.run_fast_llm_answer",
            lambda *a, **k: "基线探针 LLM 首答。",
        ),
        patch(
            "application.chat.executors.fast_lanes.fast_llm.summarize_fast_material",
            lambda *a, **k: "基线探针 LLM 首答。",
        ),
        patch(
            "application.chat.executors.fast_lanes.fast_llm.run_fast_llm_answer",
            lambda *a, **k: "基线探针 LLM 首答。",
        ),
        patch(
            "services.capabilities.document.summarize_service.summarize_document",
            lambda **k: "文档基线摘要：核心围绕架构验收。",
        ),
        patch(
            "services.capabilities.knowledge.kb_pipeline.probe_kb_capability",
            lambda *_a, **_k: kb_probe_sync_ok(),
        ),
        patch(
            "services.capabilities.web.web_orchestration_service.probe_web_capability",
            lambda url, clock=None: web_probe_sync_ok(url),
        ),
        patch(
            "services.capabilities.knowledge.kb_pipeline.fetch_kb_answer_material",
            lambda *_a, **_k: _kb_material(),
        ),
        patch(
            "services.capabilities.web.web_orchestration_service.fetch_web_evidence_block",
            lambda *_a, **_k: "[Web检索] 网页基线材料，包含网页关键词。",
        ),
        patch(
            "services.capabilities.web.web_orchestration_service.fetch_web_fast_material",
            lambda *_a, **_k: "网页基线材料，包含网页关键词。",
        ),
        patch(
            "tools.video.extract_web_video_subtitle._extract_web_video_subtitle",
            lambda *_a, **_k: SimpleNamespace(
                status="queued" if sample_id == "video_url_summary_002" else "success",
                text="视频内容围绕 Phase 10 路由与基线验收。",
                title="baseline-video",
                transcript_source="subtitle",
                metadata={"text_source": "subtitle", "background_task_id": "task-baseline-002"},
                task_id="task-baseline-002",
            ),
        ),
        patch(
            "services.capabilities.web.web_orchestration_service.fetch_web_evidence_block",
            lambda *_a, **_k: "[Web检索] 方案 B 具备更好的上线节奏。",
        ),
    ]
    lane_flags = {flag: True for flag in feature_flags.LANE_FAST_FLAG.values()}
    lane_flags["ENABLE_INGRESS_ROUTER_V2"] = True
    lane_flags["ENABLE_THREE_AGENT_AUTONOMY"] = True
    with patch.dict(feature_flags.FEATURE_FLAGS, lane_flags, clear=False):
        for item in patches:
            item.start()
        try:
            yield
        finally:
            for item in reversed(patches):
                item.stop()


def _extract_input(sample: dict[str, Any]) -> dict[str, Any]:
    inp = dict(sample.get("input") or {})
    attachments = inp.get("attachments") or []
    if attachments and inp.get("v13_file_content") is None:
        inp["v13_file_content"] = b"baseline-fixture-bytes"
    if sample["sample_id"] == "small_doc_summary_001" and not inp.get("v13_text_content"):
        inp["v13_text_content"] = "这是一个小文档，主要介绍 Phase 10 的验收目标。"
    return inp


def _estimate_tokens(text: str) -> int:
    compact = (text or "").strip()
    if not compact:
        return 0
    return max(1, len(compact) // 2)


def run_sample_perf(sample: dict[str, Any]) -> PerfRow:
    sample_id = str(sample["sample_id"])
    inp = _extract_input(sample)
    message = str(inp.get("message") or "")
    deps = _deps_for_sample(sample_id, message)

    with perf_mocks(sample_id=sample_id):
        t0 = time.perf_counter()
        result = run_agno_chat_turn_impl(
            message,
            session_id=str(inp.get("session_id") or f"baseline-{sample_id}"),
            request_id=f"baseline-{sample_id}",
            use_knowledge=bool(inp.get("use_knowledge", False)),
            v13_file_content=inp.get("v13_file_content"),
            v13_text_content=inp.get("v13_text_content"),
            deps=deps,
        )
        wall_ms = int((time.perf_counter() - t0) * 1000)

    extra = dict(result.get("extra") or {})
    first_ms = max(
        1,
        wall_ms,
        int(
            extra.get("fast_first_response_ms")
            or extra.get("elapsed_ms")
            or extra.get("timing_total_ms")
            or 0
        ),
    )
    total_ms = max(
        1,
        wall_ms,
        int(extra.get("timing_total_ms") or extra.get("elapsed_ms") or 0),
    )
    caps = list(extra.get("capabilities_called") or [])
    llm_calls = 1 if extra.get("mode") == "fast" else 2
    if extra.get("loop_id"):
        llm_calls = max(llm_calls, 3)
    tool_calls = len(caps) if caps else 0
    answer = str(result.get("answer") or "")
    token_out = _estimate_tokens(answer)
    token_in = _estimate_tokens(message) + 600
    return PerfRow(
        sample_id=sample_id,
        first_response_ms=first_ms,
        total_ms=total_ms,
        llm_calls=llm_calls,
        tool_calls=tool_calls,
        token_in=token_in,
        token_out=token_out,
        success=bool(result.get("ok")),
        lane=str(extra.get("router_lane") or extra.get("lane") or ""),
        mode=str(extra.get("mode") or ""),
    )


def run_all_samples() -> list[PerfRow]:
    return [run_sample_perf(sample) for sample in load_samples()]
