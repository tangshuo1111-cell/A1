import time

from agents import middle_agent
from application.chat.budget_clock import BudgetClock
from application.chat.chat_contracts import (
    KbSufficiencyResult,
    RetrievalSnapshot,
    SharedMaterialPrepResult,
)
from schemas import CollectionTask


def test_middle_collect_respects_channel_order(monkeypatch):
    calls: list[str] = []

    def fake_rag(task, query=None, top_k=6):
        calls.append("rag")
        return (["chunk1"], ["rag"], ["rag_try hits=1"])

    def fake_local(*_a, **_k):
        calls.append("local")
        return ([], [], False, [])

    def fake_http(*_a, **_k):
        calls.append("http")
        return ([], [], False, [])

    def fake_mcp():
        calls.append("mcp")
        return [], [], []

    monkeypatch.setattr("agents.middle_agent.collect_flow_execute._run_rag", fake_rag)
    monkeypatch.setattr("agents.middle_agent.collect_flow_execute._run_local_file_tools", fake_local)
    monkeypatch.setattr("agents.middle_agent.collect_flow_execute._run_http_tools", fake_http)
    monkeypatch.setattr("agents.middle_agent.collect_flow_execute._run_mcp", fake_mcp)
    task = CollectionTask(
        task_id="mid1",
        search_query="测试",
        collection_goal="测",
        available_channels=["rag", "tool", "mcp"],
        link_urls=[],
        enable_local_file_tools=True,
        middle_collect_priority="rag_first",
    )
    pack = middle_agent.collect(task)
    assert "rag" in calls
    assert pack.task_id == "mid1"
    assert isinstance(pack.coverage_score, float)
    assert pack.next_channel_suggestion == pack.next_best_channel


# ---------------------------------------------------------------------------
# V6 第 5 轮：MiddleAgent 已收成「可单独实例化 / 单独调用 / 单独测试」的材料裁判 Agent。
# 这一组测试不走 service，直接：MainAgent → MiddleAgent，断言 middle 自己产出判断对象。
# ---------------------------------------------------------------------------
def test_middle_agent_v6_class_can_be_instantiated_alone():
    """MiddleAgent 能脱离 service 单独实例化，且自带角色配置 / 指令。"""
    from agents.middle_agent import MiddleAgent

    mid = MiddleAgent()
    assert isinstance(mid, MiddleAgent)
    assert mid.JIESHE and "材料裁判者" in mid.JIESHE
    assert mid.ZHIDAO and "充分度" in mid.ZHIDAO
    assert mid.mingzi == "middle_agent"


def test_middle_agent_v6_class_caipan_is_self_owned_bundle():
    """MiddleAgent.caipan 是单一主入口；材料判断对象由 middle 自己产出，且尊重 main 的权限。"""
    from agents.main_agent import MainAgent
    from agents.middle_agent import AgnoMaterialBundle, CailiaoPan, MiddleAgent

    m = MainAgent()
    plan = m.pan("你好", session_id=None, http_use_knowledge=False, clock=BudgetClock.start())
    assert plan.xiezuo_pan.allow_kb is False  # 由 main 写入

    mid = MiddleAgent()
    bundle = mid.caipan("你好", plan=plan, http_use_knowledge=False, clock=BudgetClock.start())
    assert isinstance(bundle, AgnoMaterialBundle)
    assert isinstance(bundle.cailiao_pan, CailiaoPan)
    # main 不允许拉知识 → middle 自己判定 ok / 直答，没有越权
    assert bundle.cailiao_pan.bukong_xinhao == "ok"
    assert bundle.cailiao_pan.xia_yi_bu == "zhi_da"
    assert (bundle.knowledge_block or "") == ""
    assert isinstance(bundle.evidence_envelopes, list)


def test_middle_agent_v6_class_signals_que_when_kb_and_web_empty(
    monkeypatch,
):
    """有知识库意图但材料完全为空时，middle 必须自己产出『缺』信号 + 下一步建议。"""
    from agents.main_agent import MainAgent
    from agents.middle_agent import MiddleAgent

    monkeypatch.setattr(
        "services.capabilities.knowledge.rag_orchestration_service.fetch_knowledge_block",
        lambda q, top_k=5: "",
    )
    monkeypatch.setattr(
        "services.capabilities.web.web_orchestration_service.fetch_web_evidence_block",
        lambda q, max_results=3: "",
    )
    m = MainAgent()
    plan = m.pan(
        "本地肯定没有的关键词XYZABC",
        session_id=None,
        http_use_knowledge=True,
        clock=BudgetClock.start(),
    )
    assert plan.xiezuo_pan.allow_kb is True

    mid = MiddleAgent()
    bundle = mid.caipan(
        "本地肯定没有的关键词XYZABC",
        plan=plan,
        http_use_knowledge=True,
        clock=BudgetClock.start(),
    )
    cp = bundle.cailiao_pan
    assert cp.bukong_xinhao == "que"
    assert cp.que_shenme == "liangzhe"
    assert cp.xia_yi_bu in {"bu_wang", "wen_yonghu", "shou_kou"}
    kb_envs = [env for env in bundle.evidence_envelopes if env.source_type == "kb"]
    assert kb_envs
    assert kb_envs[0].status == "failed"
    assert kb_envs[0].error_code == "kb_no_match"


def test_middle_gather_parallelizes_independent_retrieval_video_paths(monkeypatch):
    """KB retrieval / web video early fetch / mcp video pending 至少不再纯串行相加。"""
    from agents.main_agent import MainAgent
    from agents.middle_agent import MiddleAgent
    from agents.middle_agent.retrieval_flow import KbRetrievalGatherOutcome
    from agents.middle_agent.runtime import MiddleAgentRuntime
    from agents.middle_agent.video_flow import EarlyWebVideoOutcome, McpVideoPendingOutcome

    monkeypatch.setattr(
        MiddleAgentRuntime,
        "shibie_save_to_kb_yitu",
        lambda self, message: False,
    )
    monkeypatch.setattr(
        MiddleAgentRuntime,
        "pan_history_followup",
        lambda self, message, history, own_mp4_in_message: (None, ""),
    )
    monkeypatch.setattr(
        MiddleAgentRuntime,
        "video_url_yitu_from_plan_or_message",
        lambda self, plan, message: (
            {"has_video_url": True, "video_url": "https://example.com/v", "yitu_label": "video_url_yitu"},
            "main",
        ),
    )
    monkeypatch.setattr(
        MiddleAgentRuntime,
        "pan_jubu_celue_video_url",
        lambda self, video_url_yitu: "call_url_fetch_video",
    )
    monkeypatch.setattr(
        "agents.middle_agent.video_flow.resolve_mcp_video_decision",
        lambda *, message, plan: (
            {"has_video": True, "mp4_path": "C:\\\\tmp\\\\a.mp4", "yitu_label": "video_yitu"},
            "call_video_to_text",
        ),
    )
    monkeypatch.setattr(
        MiddleAgentRuntime,
        "pan_jubu_celue_web",
        lambda self, intent, plan, message, http_use_knowledge, knowledge_block: (False, "skip"),
    )

    def slow_kb(*, try_rag, msg, plan, shared_prep, v8_history_used, v8_anchor, v8_followup_query, blocked_failures, is_tool_allowed):
        time.sleep(0.2)
        return KbRetrievalGatherOutcome(
            knowledge_block="kb-block",
            retrieved_chunks=[],
            v8_history_anchor_status="none",
            v14_trace_info=None,
            kb_sufficiency=None,
        )

    def slow_web_video(*, video_url_decision, video_url_yitu, plan, session_id, blocked_failures, fetch_video_text_fn):
        time.sleep(0.2)
        return EarlyWebVideoOutcome(
            early_web_video_url_normalized="https://example.com/v",
        )

    def slow_mcp_video(*, mcp_video_decision, video_yitu, plan, session_id, blocked_failures):
        time.sleep(0.2)
        return McpVideoPendingOutcome()

    monkeypatch.setattr("agents.middle_agent.coordinator.run_kb_retrieval_gather", slow_kb)
    monkeypatch.setattr("agents.middle_agent.video_flow.run_early_web_video_flow", slow_web_video)
    monkeypatch.setattr("agents.middle_agent.video_flow.run_mcp_video_tool_and_pending", slow_mcp_video)
    monkeypatch.setattr(
        "services.capabilities.web.web_orchestration_service.fetch_web_evidence_block",
        lambda q: "",
    )

    m = MainAgent()
    clock = BudgetClock.start()
    plan = m.pan("请根据知识回答并看这个视频 https://example.com/v", session_id=None, http_use_knowledge=True, clock=clock)
    mid = MiddleAgent()

    t0 = time.perf_counter()
    bundle = mid.caipan(
        "请根据知识回答并看这个视频 https://example.com/v",
        plan=plan,
        http_use_knowledge=True,
        clock=clock,
    )
    elapsed = time.perf_counter() - t0

    assert bundle.knowledge_block == "kb-block"
    assert elapsed < 0.45, f"独立 gather 路径应并发，当前耗时 {elapsed:.3f}s 看起来仍像串行"


def test_middle_web_fetch_is_not_unconditionally_parallelized_with_kb():
    from agents.middle_agent.coordinator import should_fetch_web_after_kb

    assert should_fetch_web_after_kb(
        want_web=True,
        knowledge_block="已有 KB",
        http_use_knowledge=True,
    ) is False
    assert should_fetch_web_after_kb(
        want_web=True,
        knowledge_block=None,
        http_use_knowledge=True,
    ) is True
    assert should_fetch_web_after_kb(
        want_web=True,
        knowledge_block="已有 KB",
        http_use_knowledge=False,
    ) is True


def test_middle_document_prepare_enters_parallel_coordination_without_duplicate_prepare(monkeypatch):
    from dataclasses import replace

    from agents.main_agent import MainAgent
    from agents.main_agent.schema import ExecutionAgentSpec, ExecutionPlan, V13PrepareIntent
    from agents.middle_agent import MiddleAgent
    from rag.pending_schema import SOURCE_TYPE_TEXT_FILE, PendingKnowledgeItem, SourcePayload

    calls: list[str] = []

    def fake_prepare_file_source(file_path, *, session_id, file_content=None, store=None):
        calls.append(str(file_path))
        return PendingKnowledgeItem.create(
            session_id=session_id,
            payload=SourcePayload(
                source_type=SOURCE_TYPE_TEXT_FILE,
                source_id=f"file:{file_path}",
                raw_source=str(file_path),
                title=str(file_path),
                text="文档临时材料",
                metadata={"filename": str(file_path)},
            ),
            parser_name="fake_prepare_file",
            extract_status="ok",
            error_code="",
        )

    monkeypatch.setattr(
        "services.capabilities.document.early_document_support.prepare_file_source",
        fake_prepare_file_source,
    )
    monkeypatch.setattr(
        "agents.middle_agent.pending_flow._pending_svc.prepare_file_source",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("pending_flow 不应重复 prepare_file_source")),
    )

    m = MainAgent()
    clock = BudgetClock.start()
    plan = m.pan("请先看看这个文件 report.docx", session_id=None, http_use_knowledge=False, clock=clock)
    plan = replace(
        plan,
        v13_prepare_intent=V13PrepareIntent(
            source_type=SOURCE_TYPE_TEXT_FILE,
            raw_source="report.docx",
            has_content=False,
        ),
        tools_allowed=("prepare_file",),
        execution_plan=ExecutionPlan(
            deadline_ms=20000,
            answer_policy="answer_or_partial_within_deadline",
            agents=tuple(list(plan.execution_plan.agents if plan.execution_plan else ()) + [
                ExecutionAgentSpec(name="document", timeout_ms=6000, required=False),
            ]),
            fallback="background_task_if_timeout",
        ),
    )
    assert plan.execution_plan is not None
    assert any(agent.name == "document" for agent in plan.execution_plan.agents)

    mid = MiddleAgent()
    bundle = mid.caipan(
        "请先看看这个文件 report.docx",
        plan=plan,
        http_use_knowledge=False,
        session_id="doc-early-1",
        v13_file_content=b"fake-docx-bytes",
        clock=clock,
    )

    assert len(calls) == 1
    assert bundle.pending_item is not None
    assert getattr(bundle.pending_item, "parser_name", "") == "fake_prepare_file"
    assert bundle.v13_material_status == "pending"


def test_middle_parallel_kb_gather_uses_explicit_shared_prep_across_worker_threads(monkeypatch):
    from agents.main_agent import MainAgent
    from agents.middle_agent import MiddleAgent

    shared_prep = SharedMaterialPrepResult(
        snapshot=RetrievalSnapshot(
            chunks=(),
            hits=1,
            top_score=0.91,
            evidence_tier="strong",
            strategy_requested="auto",
            strategy_used="auto:hybrid",
            rag_miss=False,
            trace_info={"strategy_used": "auto:hybrid", "hits": 1},
        ),
        kb_sufficiency=KbSufficiencyResult(
            adequate=True,
            level="sufficient",
            reason_codes=("kb_hits_ok",),
        ),
        knowledge_block="共享检索材料命中",
        material_text="共享检索材料命中",
        capabilities_called=("capability.kb",),
        trace_extra={"kb_hits": 1, "kb_evidence_tier": "strong"},
        supplementary_retrieve=False,
    )
    shared_prep = SharedMaterialPrepResult(
        snapshot=shared_prep.snapshot.__class__(
            chunks=(
                type(
                    "Chunk",
                    (),
                    {
                        "source_id": "kb:test",
                        "chunk_id": "c1",
                        "score": 0.91,
                        "retrieval_strategy": "auto:hybrid",
                        "metadata": {},
                        "to_context_line": lambda self: "共享检索材料命中",
                    },
                )(),
            ),
            hits=shared_prep.snapshot.hits,
            top_score=shared_prep.snapshot.top_score,
            evidence_tier=shared_prep.snapshot.evidence_tier,
            strategy_requested=shared_prep.snapshot.strategy_requested,
            strategy_used=shared_prep.snapshot.strategy_used,
            rag_miss=shared_prep.snapshot.rag_miss,
            trace_info=shared_prep.snapshot.trace_info,
        ),
        kb_sufficiency=shared_prep.kb_sufficiency,
        knowledge_block=shared_prep.knowledge_block,
        material_text=shared_prep.material_text,
        capabilities_called=shared_prep.capabilities_called,
        trace_extra=shared_prep.trace_extra,
        supplementary_retrieve=False,
    )

    m = MainAgent()
    clock = BudgetClock.start()
    plan = m.pan("请严格基于知识库分析当前系统问题", session_id=None, http_use_knowledge=True, clock=clock)
    mid = MiddleAgent()

    bundle = mid.caipan(
        "请严格基于知识库分析当前系统问题",
        plan=plan,
        shared_prep=shared_prep,
        http_use_knowledge=True,
        clock=clock,
    )

    assert bundle.knowledge_block == "共享检索材料命中"
    assert len(bundle.retrieved_chunks) == 1
    assert any("v12:middle:retrieved_chunks=1" in line for line in bundle.trace)


def test_middle_shared_snapshot_not_blocked_by_zero_kb_worker_budget(monkeypatch):
    from agents.main_agent import MainAgent
    from agents.middle_agent import MiddleAgent

    monkeypatch.setattr(
        "application.chat.budget_allocator.allocate_parallel_budgets",
        lambda *_a, **_k: {"web_video": 1000, "mcp_video": 1000, "document": 0, "kb": 0},
    )

    chunk = type(
        "Chunk",
        (),
        {
            "source_id": "kb:test",
            "chunk_id": "c1",
            "score": 0.88,
            "retrieval_strategy": "auto:hybrid",
            "metadata": {},
            "to_context_line": lambda self: "共享快照应被消费",
        },
    )()
    shared_prep = SharedMaterialPrepResult(
        snapshot=RetrievalSnapshot(
            chunks=(chunk,),
            hits=1,
            top_score=0.88,
            evidence_tier="strong",
            strategy_requested="auto",
            strategy_used="auto:hybrid",
            rag_miss=False,
            trace_info={"strategy_used": "auto:hybrid", "hits": 1},
        ),
        kb_sufficiency=KbSufficiencyResult(
            adequate=True,
            level="sufficient",
            reason_codes=("kb_hits_ok",),
        ),
        knowledge_block="共享快照应被消费",
        material_text="共享快照应被消费",
        capabilities_called=("capability.kb",),
        trace_extra={"kb_hits": 1, "kb_evidence_tier": "strong"},
        supplementary_retrieve=False,
    )

    m = MainAgent()
    clock = BudgetClock.start()
    plan = m.pan("请基于知识库说明当前问题", session_id=None, http_use_knowledge=True, clock=clock)
    mid = MiddleAgent()

    bundle = mid.caipan(
        "请基于知识库说明当前问题",
        plan=plan,
        shared_prep=shared_prep,
        http_use_knowledge=True,
        clock=clock,
    )

    assert len(bundle.retrieved_chunks) == 1
    assert not any("tool=kb reason=parallel_budget_zero" in line for line in bundle.trace)


def test_web_video_main_path_prefers_tool_chain_and_preserves_task_refs(monkeypatch):
    from agents.main_agent import MainAgent
    from agents.middle_agent.video_flow import run_early_web_video_flow
    from tools.video.tool_result import VideoToolResult

    def fake_tool(*, url: str, session_id: str):
        return VideoToolResult(
            tool_name="extract_web_video_subtitle",
            source_type="web_video",
            source_ref=url,
            title="视频标题",
            task_id="web-task-123",
            status="queued",
            metadata={
                "background_task_id": "web-task-123",
                "title": "视频标题",
                "duration": 366.0,
                "sync_strategy": "background_after_probe",
                "capability_suggested_mode": "demote_to_async",
                "capability_reason": "duration_over_short_threshold",
            },
        )

    def slow_probe(url, *, prefer_subtitles=True, allow_asr=False):
        time.sleep(0.15)
        raise AssertionError("工具链 queued 后主链不应继续等待慢探测结果")

    monkeypatch.setattr("services.capabilities.video.web_video_gather.run_web_video_tool", fake_tool)
    monkeypatch.setattr(
        "services.capabilities.video.web_video_gather.run_fast_subtitle_probe",
        lambda *, url, fetch_fn: slow_probe(url, prefer_subtitles=True, allow_asr=False),
    )
    monkeypatch.setattr("agents.middle_agent.video_flow._is_tool_allowed", lambda plan, tool_name: True)

    plan = MainAgent().pan(
        "看看这个视频 https://example.com/v",
        session_id=None,
        http_use_knowledge=False,
        clock=BudgetClock.start(),
    )
    out = run_early_web_video_flow(
        video_url_decision="call_url_fetch_video",
        video_url_yitu={"has_video_url": True, "video_url": "https://example.com/v", "yitu_label": "video_url_yitu"},
        plan=plan,
        session_id="sess-web-main",
        blocked_failures=[],
    )

    assert out.video_url_result is not None
    assert out.video_url_result.success is False
    assert out.video_url_result.error == "background_queued"
    assert out.web_video_pending_early is not None
    assert getattr(out.web_video_pending_early, "source_type", "") == "web_video"
    assert getattr(out.web_video_pending_early, "metadata", {}).get("task_id") == "web-task-123"


def test_web_video_main_path_can_use_tool_chain_asr_success(monkeypatch):
    from agents.main_agent import MainAgent
    from agents.middle_agent.video_flow import run_early_web_video_flow
    from tools.video.tool_result import VideoToolResult
    from video.fetch_result import FetchVideoResult

    def fake_tool(*, url: str, session_id: str):
        return VideoToolResult(
            tool_name="extract_web_video_subtitle",
            source_type="web_video",
            source_ref=url,
            title="视频标题",
            task_id="web-task-456",
            status="success",
            text="这是转写文本",
            transcript_source="asr",
            metadata={
                "provider": "tencent_flash",
                "model": "flash",
                "duration": 48.0,
                "sync_strategy": "sync_asr_after_probe",
            },
        )

    def slow_probe(*, url: str, fetch_fn):
        time.sleep(0.15)
        return FetchVideoResult.failure(stage="subtitle", error="probe_slow", source_url=url)

    monkeypatch.setattr("services.capabilities.video.web_video_gather.run_web_video_tool", fake_tool)
    monkeypatch.setattr("services.capabilities.video.web_video_gather.run_fast_subtitle_probe", slow_probe)
    monkeypatch.setattr("agents.middle_agent.video_flow._is_tool_allowed", lambda plan, tool_name: True)

    plan = MainAgent().pan(
        "看看这个视频 https://example.com/v",
        session_id=None,
        http_use_knowledge=False,
        clock=BudgetClock.start(),
    )
    out = run_early_web_video_flow(
        video_url_decision="call_url_fetch_video",
        video_url_yitu={"has_video_url": True, "video_url": "https://example.com/v", "yitu_label": "video_url_yitu"},
        plan=plan,
        session_id="sess-web-main",
        blocked_failures=[],
    )

    assert out.video_url_result is not None
    assert out.video_url_result.success is True
    assert out.video_url_result.text_source == "asr"
    assert out.video_url_result.asr_provider == "tencent_flash"
    assert out.web_video_pending_early is not None
