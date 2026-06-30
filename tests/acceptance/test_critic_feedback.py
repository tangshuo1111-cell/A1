from __future__ import annotations

import functools
import http.server
import socketserver
import threading
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace


def _serve(tmp_path: Path):
    (tmp_path / "a.html").write_text(
        "<html><head><title>A Article</title></head><body><article>"
        "<h1>A Article</h1><p>A argues that public AI tools improve access and speed. "
        "Its advantage is broad reach and practical productivity. Its limitation is privacy risk.</p></article></body></html>",
        encoding="utf-8",
    )
    (tmp_path / "b.html").write_text(
        "<html><head><title>B Article</title></head><body><article>"
        "<h1>B Article</h1><p>B argues that AI adoption should be cautious and governed. "
        "Its advantage is risk awareness and institutional control. Its limitation is slower experimentation.</p></article></body></html>",
        encoding="utf-8",
    )
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(tmp_path))
    server = socketserver.TCPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def _question(base: str, second: str = "b.html") -> str:
    return (
        "请对比这两个网页分别表达了什么，它们的角度、优点和局限有什么不同：\n"
        f"{base}/a.html\n{base}/{second}"
    )


def test_successful_compare_generates_matrix_and_critic(tmp_path):
    from services.agno_chat_service import run_agno_chat_turn

    server, base = _serve(tmp_path)
    try:
        out = run_agno_chat_turn(_question(base), session_id="v17r2-success")
    finally:
        server.shutdown()
    extra = out["extra"]
    assert extra["comparison_matrix"]["status"] == "ready"
    assert extra["critic_check"]["critic_check_id"]
    assert extra.get("feedback_request") is None
    assert 0 in extra["used_rounds"]


def test_partial_compare_triggers_feedback_and_conservative_answer(tmp_path, monkeypatch):
    from config import feature_flags
    from services.agno_chat_service import run_agno_chat_turn

    monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_COMPLEX_REFINE_V2", False)
    server, base = _serve(tmp_path)
    try:
        out = run_agno_chat_turn(_question(base, "missing.html"), session_id="v17r2-partial")
    finally:
        server.shutdown()
    extra = out["extra"]
    assert extra["feedback_request"]["feedback_request_id"]
    assert extra["feedback_gate_result"]["allowed"] is True
    assert extra["round_delta"]["job_id"]
    assert "保守" in extra["final_answer"] or "补抓" in extra["final_answer"]


def test_gate_rejects_when_privacy_scope_blocks_external_processing(tmp_path):
    from agents.answer_agent import AnswerAgent
    from agents.main_agent import MainAgent
    from agents.middle_agent import MiddleAgent
    from application.chat.budget_clock import BudgetClock
    from services.execution.feedback_gate import evaluate_feedback_request

    server, base = _serve(tmp_path)
    try:
        msg = _question(base, "missing.html")
        clock = BudgetClock.start()
        plan = MainAgent().pan(msg, session_id="v17r2-private", clock=clock).plan
        private_plan = replace(plan, privacy_scope="private_sensitive")
        bundle = MiddleAgent().caipan(msg, plan=private_plan, clock=clock).bundle
        review = AnswerAgent().review_multisource(msg, plan=private_plan, bundle=bundle, current_round=0)
        gate = evaluate_feedback_request(
            feedback_request=review["feedback_request"],
            fallback_steps=private_plan.fallback_steps,
            tools_allowed=list((private_plan.tool_plan or {}).get("tools_allowed", [])),
            privacy_scope=private_plan.privacy_scope,
            budget_policy=private_plan.budget_policy,
            max_rounds=private_plan.max_rounds,
            current_round=0,
        )
    finally:
        server.shutdown()
    assert gate["allowed"] is False
    assert gate["reason"] in {"all_requested_steps_blocked", "fallback_not_allowed_by_main"}
    assert gate["policy_violations"]


def test_gate_rejects_when_feedback_changes_intent():
    from services.execution.feedback_gate import evaluate_feedback_request

    gate = evaluate_feedback_request(
        feedback_request={
            "feedback_request_id": "fbreq_demo",
            "job_id": "job1",
            "round_index": 0,
            "reason": "need_more",
            "evidence_gap": "gap",
            "query_hint": "请帮我顺便查第三个网站",
            "requested_source_task_ids": ["src1"],
            "requested_fallback_step_ids": ["step1"],
            "material_sufficiency_before": "insufficient",
            "original_user_intent": "请对比两个网页",
            "status": "requested",
        },
        fallback_steps=[{"step_id": "step1", "tool_name": "fetch_dynamic_page"}],
        tools_allowed=["fetch_dynamic_page"],
        privacy_scope="public_web",
        budget_policy={},
        max_rounds=1,
        current_round=0,
    )
    assert gate["allowed"] is False
    assert gate["reason"] == "intent_changed"


def test_round1_success_uses_round1_material(tmp_path, monkeypatch):
    """Round1 应消费 fallback 抓取到的第二个来源材料（与真实 Playwright 无关）。"""
    from config import feature_flags
    from services.agno_chat_service import run_agno_chat_turn

    monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_COMPLEX_REFINE_V2", False)
    from tools.web import registry as web_registry
    from tools.web.common import content_hash, now_iso
    from tools.web.quality import assess_web_text
    from tools.web.tool_result import WebToolResult

    server, base = _serve(tmp_path)
    original = web_registry.call_tool

    # 与 _serve() 写入的 b.html 正文语义一致（静态路径故意失败 → 动态补抓须成功）
    b_extracted_text = (
        "B Article\n\nB argues that AI adoption should be cautious and governed. "
        "Its advantage is risk awareness and institutional control. Its limitation is slower experimentation."
    )

    def fake_call_tool(name: str, **kwargs):
        url = kwargs.get("url", "")
        if name == "fetch_web_page" and url.endswith("/b.html"):
            return SimpleNamespace(
                status="failed",
                error_code="forced_static_fail",
                failure_reason="forced_static_fail",
                metadata={},
                text="",
                pending_id="",
                source_id="",
                retrieved_chunk_ids=[],
                title="",
                url=url,
            )
        if name == "fetch_dynamic_page" and url.rstrip("/").endswith("b.html"):
            q = assess_web_text(b_extracted_text)
            metadata = {
                "url": url,
                "final_url": url,
                "domain": "127.0.0.1",
                "title": "B Article",
                "source_type": "web_url",
                "extraction_method": "playwright_bs4",
                "fetch_method": "dynamic",
                "parser_name": "fetch_dynamic_page",
                "content_hash": content_hash(b_extracted_text),
                "text_length": len(b_extracted_text),
                "quality_level": q.get("quality_level", ""),
                "retrieved_at": now_iso(),
                "requires_cookie": False,
                "cookie_used": False,
                "mcp_mode": "mcp_compatible_adapter",
            }
            return WebToolResult(
                tool_name="fetch_dynamic_page",
                status="success",
                url=url,
                final_url=url,
                domain="127.0.0.1",
                title="B Article",
                text=b_extracted_text,
                metadata=metadata,
                quality=q,
                warnings=list(q.get("warnings", []) or []),
                extraction_method="playwright_bs4",
                fetch_method="dynamic",
                trace=["test:stub_fetch_dynamic_success_b_html"],
            )
        return original(name, **kwargs)

    monkeypatch.setattr(web_registry, "call_tool", fake_call_tool)
    try:
        out = run_agno_chat_turn(_question(base), session_id="v17r2-round1")
    finally:
        server.shutdown()
    extra = out["extra"]
    assert extra["feedback_gate_result"]["allowed"] is True
    assert extra["round_delta"]["new_source_briefs"]
    assert extra["final_answer_based_on_round"] == "round_1"
    assert extra["used_rounds"] == [0, 1]


def test_default_chain_builds_feedback_request_and_round1_web(monkeypatch):
    from threading import Lock

    from agents.answer_agent import AnswerAgent
    from config import feature_flags

    monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_COMPLEX_REFINE_V2", False)
    from agents.main_agent.schema import AgnoCollaborationPlan, MainXiezuoPan
    from agents.middle_agent.schema import AgnoMaterialBundle, CailiaoPan, EvidenceEnvelope
    from application.chat.run_chat_turn import ChatTurnDeps, run_agno_chat_turn_impl
    from schemas import MainDecision

    plan = AgnoCollaborationPlan(
        decision=MainDecision(task_id="default-fb-1", task_status="routed"),
        force_skip_evidence=False,
        web_supplement_mode="on_kb_miss_or_hint",
        answer_composition="default",
        xiezuo_pan=MainXiezuoPan(
            renwu_lei="zhishu",
            zhengju_need=True,
            allow_kb=True,
            allow_web=True,
            fengxian_yinzi=0.5,
            celue_tag="kb_web",
        ),
        needs_retrieval=True,
        retrieval_strategy="auto",
        needs_pending=False,
        pending_reference="none",
        answer_mode="knowledge_grounded",
        tools_allowed=("fetch_web",),
        max_rounds=1,
        original_user_intent="项目代号是什么",
    )

    bundle = AgnoMaterialBundle(
        knowledge_block="",
        web_block="",
        trace=[],
        knowledge_adequate=False,
        material_still_insufficient=True,
        web_judgment_reason="skip",
        kb_evidence_tier="none",
        insufficiency_signal="still_empty_after_gather",
        cailiao_pan=CailiaoPan(
            gou=False,
            kb_qiangdu=0.0,
            bukong_xinhao="que",
            laiyuan_zhu="wu",
            use_kb=True,
            use_web=False,
            que_shenme="liangzhe",
            xia_yi_bu="bu_wang",
        ),
        material_sufficiency="insufficient",
        evidence_envelopes=[EvidenceEnvelope(source_type="kb", status="failed", error_code="kb_no_match")],
        critic_check={
            "critic_check_id": "critic_default",
            "revision_required": True,
            "safe_to_answer": False,
            "limitations": ["当前没有成功证据来源，最终回答必须保守说明。"],
        },
        answer_limitations=["当前没有成功证据来源，最终回答必须保守说明。"],
    )

    main = SimpleNamespace(pan=lambda *a, **k: plan)
    middle = SimpleNamespace(caipan=lambda *a, **k: bundle)
    answer = AnswerAgent()
    monkeypatch.setattr(
        "services.capabilities.web.web_orchestration_service.fetch_web_evidence_block",
        lambda message, max_results=3: "[Web检索] 项目代号是 Atlas",
    )

    deps = ChatTurnDeps(
        histories={},
        session_prev_video={},
        session_pending_video={},
        lock=Lock(),
        main_agent=main,
        middle_agent=middle,
        answer_agent=answer,
        run_basic_qa=lambda *a, **k: "基于补充网页证据，项目代号是 Atlas。",
        path_fingerprint=lambda *a, **k: "fp",
        nodes_contract=lambda tr: {},
    )

    out = run_agno_chat_turn_impl("请根据知识库和网页证据回答：项目代号是什么", session_id="default-fb", deps=deps)
    extra = out["extra"]
    assert extra["feedback_request"]["feedback_request_id"]
    assert extra["feedback_gate_result"]["allowed"] is True
    assert extra["used_rounds"] == [0, 1]
    assert extra["final_answer_based_on_round"] == "round_1"
    assert extra["v15_tool_calls"][-1]["tool"] == "fetch_web"
