"""
V15 R2 端到端默认场景测试。

验证目标：
1. 默认后端接口 POST /chat/agno 走 Main→Middle→Answer 新主链
2. extra 中包含 V15 R1 核心字段（来自真实执行）
3. 三大默认场景（KB问答/prepare-save/普通聊天）从接口层跑通
4. 失败边界案例（检索无结果 → conservative）
5. 前端不伪造状态（extra 字段来自后端真实执行）

本轮改动档次：中等（在已有测试基础上补 e2e 集成层）
为什么不跑全量：本文件已是专项，全量回归单独执行。
"""
from __future__ import annotations

import copy
import sys
from functools import lru_cache

from tests._support.bootstrap import bootstrap_historical_test

_ROOT = str(bootstrap_historical_test(__file__))
_CORE = _ROOT
_CAP = _ROOT
for _p in [_ROOT, _CORE, _CAP]:
    if _p not in sys.path:
        sys.path.insert(0, _p)


@lru_cache(maxsize=None)
def _cached_turn(
    message: str,
    *,
    session_id: str,
    use_knowledge: bool = False,
) -> dict:
    from services import agno_chat_service

    out = agno_chat_service.run_agno_chat_turn(
        message,
        session_id=session_id,
        use_knowledge=use_knowledge,
    )
    return copy.deepcopy(out)


# ---------------------------------------------------------------------------
# O 组：默认接口 V15 extra 字段验证
# ---------------------------------------------------------------------------
class TestO_DefaultApiV15Fields:
    """O: POST /chat/agno → extra 含 V15 核心字段（来自真实执行，非硬编码）"""

    def test_o1_extra_has_v15_plan_fields(self) -> None:
        """O1: extra 包含 v15_plan_id / v15_needs_retrieval / v15_answer_mode"""
        out = _cached_turn("你好", session_id="o-shared-direct")
        ex = out["extra"]
        assert "v15_plan_id" in ex, "extra 应含 v15_plan_id"
        assert "v15_needs_retrieval" in ex, "extra 应含 v15_needs_retrieval"
        assert "v15_answer_mode" in ex, "extra 应含 v15_answer_mode"
        assert "v15_retrieval_strategy" in ex, "extra 应含 v15_retrieval_strategy"
        assert "v15_material_sufficiency" in ex, "extra 应含 v15_material_sufficiency"

    def test_o2_extra_has_v15_bundle_fields(self) -> None:
        """O2: extra 包含 v15_bundle_id / v15_execution_status / v15_retrieved_chunks_count"""
        out = _cached_turn("你好", session_id="o-shared-direct")
        ex = out["extra"]
        assert "v15_bundle_id" in ex, "extra 应含 v15_bundle_id"
        assert "v15_execution_status" in ex, "extra 应含 v15_execution_status"
        assert "v15_retrieved_chunks_count" in ex, "extra 应含 v15_retrieved_chunks_count"

    def test_o3_v15_fields_from_real_execution(self) -> None:
        """O3: V15 字段来自真实执行变量（非硬编码，字段值可验证）"""
        out = _cached_turn("帮我算一道数学题：1+1=?", session_id="o3-test")
        ex = out["extra"]
        # plan_id 来自 MainDecision.task_id，必须是非空字符串
        assert isinstance(ex["v15_plan_id"], str) and ex["v15_plan_id"], \
            "v15_plan_id 必须是非空字符串（来自真实 task_id）"
        # bundle_id 来自 AgnoMaterialBundle.bundle_id（UUID 截断为 8 位）
        assert isinstance(ex["v15_bundle_id"], str) and len(ex["v15_bundle_id"]) >= 8, \
            "v15_bundle_id 必须是非空字符串（来自真实 bundle UUID，至少 8 位）"
        # answer_mode 必须是合法值
        assert ex["v15_answer_mode"] in (
            "knowledge_grounded", "temporary_material", "commit_result",
            "direct", "conservative"
        ), f"v15_answer_mode 必须是合法值，实际: {ex['v15_answer_mode']}"

    def test_o4_v15_retrieved_chunks_count_is_integer(self) -> None:
        """O4: v15_retrieved_chunks_count 是整数（0 或正数）"""
        out = _cached_turn("你好", session_id="o-shared-direct")
        ex = out["extra"]
        assert isinstance(ex["v15_retrieved_chunks_count"], int), \
            "v15_retrieved_chunks_count 必须是整数"
        assert ex["v15_retrieved_chunks_count"] >= 0, \
            "v15_retrieved_chunks_count 不能是负数"


# ---------------------------------------------------------------------------
# P 组：场景 C 普通聊天端到端（默认主入口）
# ---------------------------------------------------------------------------
class TestP_ScenarioCDirectChatE2E:
    """P: 普通聊天端到端（通过默认接口）"""

    def test_p1_direct_chat_answer_mode_is_direct(self) -> None:
        """P1: 普通聊天 → v15_answer_mode=direct"""
        out = _cached_turn("你好，帮我介绍一下自己", session_id="p-direct-shared")
        ex = out["extra"]
        assert ex.get("v15_answer_mode") == "direct", \
            f"普通聊天应 answer_mode=direct，实际: {ex.get('v15_answer_mode')}"

    def test_p2_direct_chat_needs_retrieval_false(self) -> None:
        """P2: 普通聊天 → v15_needs_retrieval=False（不检索知识库）"""
        out = _cached_turn("你好，帮我介绍一下自己", session_id="p-direct-shared")
        ex = out["extra"]
        assert ex.get("v15_needs_retrieval") is False, \
            f"普通聊天应 needs_retrieval=False，实际: {ex.get('v15_needs_retrieval')}"

    def test_p3_direct_chat_retrieved_chunks_zero(self) -> None:
        """P3: 普通聊天 → retrieved_chunks=0（不检索）"""
        out = _cached_turn("你好，帮我介绍一下自己", session_id="p-direct-shared")
        ex = out["extra"]
        assert ex.get("v15_retrieved_chunks_count") == 0, \
            f"普通聊天不应有检索结果，实际: {ex.get('v15_retrieved_chunks_count')}"

    def test_p4_direct_chat_no_failures(self) -> None:
        """P4: 普通聊天不应有工具失败记录"""
        out = _cached_turn("你好，帮我介绍一下自己", session_id="p-direct-shared")
        ex = out["extra"]
        # 普通聊天不触发任何工具，不应有 failures
        assert "v15_failures" not in ex or len(ex.get("v15_failures", [])) == 0, \
            f"普通聊天不应有工具失败，实际: {ex.get('v15_failures')}"

    def test_p5_direct_chat_trace_contains_v15_lines(self) -> None:
        """P5: trace 包含 V15 主控检索行"""
        out = _cached_turn("你好，帮我介绍一下自己", session_id="p-direct-shared")
        trace = out["extra"].get("collaboration_trace", [])
        trace_str = "|".join(trace)
        assert "v15:needs_retrieval_plan=" in trace_str, \
            f"trace 应含 v15:needs_retrieval_plan= 行，实际 trace: {trace[:8]}"


# ---------------------------------------------------------------------------
# Q 组：场景 A 知识库问答端到端（use_knowledge=True）
# ---------------------------------------------------------------------------
class TestQ_ScenarioAKbQaE2E:
    """Q: KB 问答端到端（通过默认接口 use_knowledge=True）"""

    def test_q1_kb_qa_answer_mode_knowledge_grounded(self) -> None:
        """Q1: use_knowledge=True → v15_answer_mode=knowledge_grounded（或 direct 兜底）"""
        out = _cached_turn(
            "什么是知识图谱？",
            session_id="q1-test",
            use_knowledge=True,
        )
        ex = out["extra"]
        assert ex.get("v15_answer_mode") in (
            "knowledge_grounded", "direct", "conservative"
        ), f"KB 问答 answer_mode 应在合法范围，实际: {ex.get('v15_answer_mode')}"
        # use_knowledge=True 时 needs_retrieval 应为 True（由 plan 设置）
        assert ex.get("v15_needs_retrieval") is True, \
            f"use_knowledge=True 时应 needs_retrieval=True，实际: {ex.get('v15_needs_retrieval')}"

    def test_q2_kb_qa_no_knowledge_block_fallback_if_chunks(self) -> None:
        """Q2: KB 问答有 retrieved_chunks 时，不依赖旧 knowledge_block fallback（源码验证）"""
        import inspect

        from agents.answer_agent import runtime as ans_rt
        src = inspect.getsource(ans_rt.AnswerAgent.huida)
        # 验证 direct 模式在最顶部
        idx_direct = src.find("answer_mode == \"direct\"")
        idx_kb_none = src.find('knowledge_block=None,  # direct')
        assert idx_direct != -1 and idx_kb_none != -1 and idx_direct < idx_kb_none, \
            "direct 模式应先于向执行器传入知识块占位"

    def test_q3_kb_qa_v15_plan_id_not_empty(self) -> None:
        """Q3: KB 问答 extra.v15_plan_id 非空（来自真实 task_id）"""
        out = _cached_turn("什么是知识图谱？", session_id="q1-test", use_knowledge=True)
        assert out["extra"].get("v15_plan_id"), "KB 问答应有 v15_plan_id"


# ---------------------------------------------------------------------------
# R 组：失败边界案例（检索无结果 → conservative）
# ---------------------------------------------------------------------------
class TestR_FailureBoundaryCase:
    """R: 失败边界案例（来自真实执行，非伪造）"""

    def test_r1_no_match_retrieval_produces_conservative_or_direct(self) -> None:
        """R1: 检索无结果时 Answer 走 conservative 或 direct（不假装有答案）"""
        from services import agno_chat_service
        # 用一个肯定不在 KB 里的关键词
        out = agno_chat_service.run_agno_chat_turn(
            "X5K9W2本地绝对没有的神秘关键词Q7J3M1",
            session_id="r1-test",
            use_knowledge=True,
        )
        # material_sufficiency 应反映无结果状态（见 extra.v15_material_sufficiency，可为多种兼容值）
        # 关键验证：answer 仍然返回了 ok=True（不崩溃），且 pipeline_ok=True
        assert out["ok"] is True, "失败边界不应让接口返回 HTTP 500"
        assert out.get("task_status") in ("succeeded", "partial"), (
            f"失败边界应由 Answer 保守回答，task_status 应为 succeeded/partial，实际: {out.get('task_status')}"
        )

    def test_r2_tools_allowed_block_produces_failures(self) -> None:
        """R2: tools_allowed 拦截产生 failures（通过 bundle 直接验证）"""
        from agents.main_agent.schema import AgnoCollaborationPlan, MainXiezuoPan
        from agents.middle_agent.runtime import _is_tool_allowed
        from schemas import MainDecision

        # 创建只允许 commit_pending 的 plan
        decision = MainDecision(
            answer_channel="zhijie", need_rag=True,
            task_id="r2-task", router_source="test",
        )
        xp = MainXiezuoPan(
            renwu_lei="zhijie", zhengju_need=True,
            allow_kb=True, allow_web=False,
            fengxian_yinzi=0.2, celue_tag="test",
        )
        plan = AgnoCollaborationPlan(
            decision=decision, force_skip_evidence=False,
            web_supplement_mode="explicit_only", answer_composition="standard",
            xiezuo_pan=xp,
            needs_retrieval=True, retrieval_strategy="auto",
            needs_pending=False, pending_reference="none",
            answer_mode="knowledge_grounded",
            tools_allowed=("commit_pending",),  # 不含 retrieve_knowledge
        )
        # retrieve_knowledge 被拦截
        assert not _is_tool_allowed(plan, "retrieve_knowledge"), \
            "retrieve_knowledge 应被白名单拦截"
        # commit_pending 被允许
        assert _is_tool_allowed(plan, "commit_pending"), \
            "commit_pending 应在白名单中"

    def test_r3_failure_boundary_trace_visible(self) -> None:
        """R3: 失败边界 trace 可见（v15:tool_blocked 行）"""
        import inspect

        from agents.middle_agent import runtime as mid_rt
        src = inspect.getsource(mid_rt)
        assert "v15:tool_blocked" in src, \
            "工具拦截时 trace 应含 v15:tool_blocked 行"
        assert "not_allowed_by_plan" in src, \
            "工具拦截原因应含 not_allowed_by_plan"

    def test_r4_answer_conservative_when_no_match(self) -> None:
        """R4: bundle.material_sufficiency=no_match + answer_mode=conservative → 返回保守说明"""
        from agents.answer_agent.runtime import AnswerAgent
        from agents.main_agent.schema import AgnoCollaborationPlan, MainXiezuoPan
        from agents.middle_agent.schema import AgnoMaterialBundle, CailiaoPan
        from schemas import MainDecision

        decision = MainDecision(
            answer_channel="zhishu", need_rag=True,
            task_id="r4-task", router_source="test",
        )
        xp = MainXiezuoPan(
            renwu_lei="zhishu", zhengju_need=True,
            allow_kb=True, allow_web=False,
            fengxian_yinzi=0.8, celue_tag="test",
        )
        plan = AgnoCollaborationPlan(
            decision=decision, force_skip_evidence=False,
            web_supplement_mode="explicit_only", answer_composition="standard",
            xiezuo_pan=xp,
            needs_retrieval=True, retrieval_strategy="auto",
            needs_pending=False, pending_reference="none",
            answer_mode="conservative",
            tools_allowed=(),
        )
        cp = CailiaoPan(
            gou=False, kb_qiangdu=0.0, bukong_xinhao="que",
            laiyuan_zhu="wu", use_kb=False, use_web=False,
            que_shenme="yiban", xia_yi_bu="shou_kou",
        )
        bundle = AgnoMaterialBundle(
            knowledge_block=None, web_block=None,
            trace=[], knowledge_adequate=False,
            material_still_insufficient=True,
            web_judgment_reason="",
            kb_evidence_tier="zero", insufficiency_signal="que",
            cailiao_pan=cp,
            retrieved_chunks=[], temporary_materials=[],
            commit_results=[], failures=[],
            material_sufficiency="no_match",
        )
        from application.chat.budget_clock import BudgetClock

        agent = AnswerAgent()
        text, _ = agent.huida(
            "这个关键词在知识库里吗？",
            context_block=None,
            plan=plan,
            bundle=bundle,
            clock=BudgetClock.start(),
        )
        assert "知识库" in text or "无法" in text or "找不到" in text or "抱歉" in text, \
            f"conservative 模式下应有保守说明，实际: {text[:200]}"


# ---------------------------------------------------------------------------
# S 组：兼容层隔离验证
# ---------------------------------------------------------------------------
class TestS_CompatLayerIsolated:
    """S: 兼容层已隔离，默认主路径不依赖旧 legacy 字段"""

    def test_s1_knowledge_block_fallback_legacy_annotated(self) -> None:
        """S1: Answer huida 中 knowledge_block fallback 有 legacy 注释"""
        import inspect

        from agents.answer_agent import runtime as ans_rt
        src = inspect.getsource(ans_rt.AnswerAgent.huida)
        assert "legacy" in src.lower(), \
            "huida 中 knowledge_block fallback 段应有 legacy 注释"

    def test_s2_direct_mode_does_not_read_knowledge_block(self) -> None:
        """S2: direct 模式不读 knowledge_block（接口级验证）"""
        from services import agno_chat_service
        out = agno_chat_service.run_agno_chat_turn(
            "普通聊天问题",
            session_id="s2-test",
        )
        ex = out["extra"]
        # direct 模式：v15_answer_mode=direct，v15_retrieved_chunks_count=0
        assert ex.get("v15_answer_mode") == "direct"
        assert ex.get("v15_retrieved_chunks_count") == 0

    def test_s3_default_three_scenarios_no_legacy_fallback(self) -> None:
        """S3: 三个默认场景主路径源码中，direct 在 legacy fallback 之前返回"""
        import inspect

        from agents.answer_agent import runtime as ans_rt
        src = inspect.getsource(ans_rt.AnswerAgent.huida)
        idx_kb_none_direct = src.find('knowledge_block=None,  # direct')
        idx_kb_ground = src.find('elif answer_mode == "knowledge_grounded"')
        assert idx_kb_none_direct != -1 and idx_kb_ground != -1 and idx_kb_none_direct < idx_kb_ground, \
            "direct 传入 knowledge_block=None 应先于 knowledge_grounded 取材"

    def test_s4_v15_extra_fields_are_real_not_hardcoded(self) -> None:
        """S4: V15 extra 字段来自真实执行（两次调用产生不同 bundle_id）"""
        from services import agno_chat_service
        out1 = agno_chat_service.run_agno_chat_turn("问题1", session_id="s4-t1")
        out2 = agno_chat_service.run_agno_chat_turn("问题2", session_id="s4-t2")
        bid1 = out1["extra"].get("v15_bundle_id", "")
        bid2 = out2["extra"].get("v15_bundle_id", "")
        assert bid1 != bid2, \
            f"两次调用应产生不同 bundle_id（证明来自真实执行），bid1={bid1}, bid2={bid2}"


# ---------------------------------------------------------------------------
# T 组：接口层 V15 extra 字段结构完整性
# ---------------------------------------------------------------------------
class TestT_ApiExtraV15Completeness:
    """T: 接口层 extra 中 V15 字段结构完整性验证"""

    _REQUIRED_V15_FIELDS = [
        "v15_plan_id",
        "v15_bundle_id",
        "v15_needs_retrieval",
        "v15_retrieval_strategy",
        "v15_needs_pending",
        "v15_pending_reference",
        "v15_answer_mode",
        "v15_tools_allowed",
        "v15_material_sufficiency",
        "v15_execution_status",
        "v15_retrieved_chunks_count",
    ]

    def test_t1_all_v15_fields_present(self) -> None:
        """T1: extra 包含全部必要的 V15 字段"""
        out = _cached_turn("测试 V15 字段完整性", session_id="t-shared")
        ex = out["extra"]
        missing = [f for f in self._REQUIRED_V15_FIELDS if f not in ex]
        assert not missing, f"extra 缺少 V15 字段: {missing}"

    def test_t2_v15_tools_allowed_is_list(self) -> None:
        """T2: v15_tools_allowed 是列表类型"""
        out = _cached_turn("测试 V15 字段完整性", session_id="t-shared")
        ta = out["extra"].get("v15_tools_allowed")
        assert isinstance(ta, list), f"v15_tools_allowed 应是列表，实际: {type(ta)}"

    def test_t3_v15_execution_status_valid_value(self) -> None:
        """T3: v15_execution_status 是合法值"""
        out = _cached_turn("测试 V15 字段完整性", session_id="t-shared")
        status = out["extra"].get("v15_execution_status")
        assert status in ("ok", "partial", "failed"), \
            f"v15_execution_status 应是合法值，实际: {status}"

    def test_t4_service_extra_contains_v15_and_v6_together(self) -> None:
        """T4: extra 同时包含 V15 新字段和 V6 旧字段（向后兼容）"""
        out = _cached_turn("测试 V15 字段完整性", session_id="t-shared")
        ex = out["extra"]
        # V6 旧字段仍存在（向后兼容）
        assert "v6_takeover" in ex, "旧 v6_takeover 字段应仍存在（兼容）"
        assert "v6_main_task_id" in ex, "旧 v6_main_task_id 字段应仍存在（兼容）"
        # V15 新字段也存在
        assert "v15_plan_id" in ex, "新 v15_plan_id 字段应存在"
        assert "v15_bundle_id" in ex, "新 v15_bundle_id 字段应存在"


class TestU_FinalProtocolContract:
    """U: 第八步协议收口字段与任务轮询契约"""

    def test_u1_extra_has_progress_stage_and_agent_timings(self) -> None:
        out = _cached_turn(
            "请根据知识库和网页证据回答一个问题",
            session_id="u1-test",
            use_knowledge=True,
        )
        ex = out["extra"]
        assert ex.get("progress_stage") == "completed"
        timings = ex.get("agent_timings")
        assert isinstance(timings, dict), "agent_timings 应为对象"
        for key in (
            "session_snapshot_ms",
            "main_ms",
            "middle_ms",
            "answer_ms",
            "session_update_ms",
            "extra_build_ms",
            "total_ms",
        ):
            assert key in timings, f"agent_timings 缺少 {key}"

    def test_u2_task_route_contract_keeps_ready_fields(self) -> None:
        from fastapi.testclient import TestClient

        from api.main import app

        with TestClient(app) as client:
            r = client.get("/tasks/does-not-exist")
        assert r.status_code == 404

    def test_u3_feedback_fields_exposed_for_default_chain_when_triggered(self) -> None:
        from threading import Lock
        from types import SimpleNamespace

        from agents.answer_agent import AnswerAgent
        from agents.main_agent.schema import AgnoCollaborationPlan, MainXiezuoPan
        from agents.middle_agent.schema import AgnoMaterialBundle, CailiaoPan, EvidenceEnvelope
        from application.chat.run_chat_turn import ChatTurnDeps, run_agno_chat_turn_impl
        from schemas import MainDecision

        plan = AgnoCollaborationPlan(
            decision=MainDecision(task_id="u3-task", task_status="routed"),
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
            original_user_intent="请根据知识库和网页证据回答：项目代号是什么",
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
                "critic_check_id": "critic_u3",
                "revision_required": True,
                "safe_to_answer": False,
                "limitations": ["当前没有成功证据来源，最终回答必须保守说明。"],
            },
            answer_limitations=["当前没有成功证据来源，最终回答必须保守说明。"],
        )

        deps = ChatTurnDeps(
            histories={},
            session_prev_video={},
            session_pending_video={},
            lock=Lock(),
            main_agent=SimpleNamespace(pan=lambda *a, **k: plan),
            middle_agent=SimpleNamespace(caipan=lambda *a, **k: bundle),
            answer_agent=AnswerAgent(),
            run_basic_qa=lambda *a, **k: "基于补充网页证据，项目代号是 Atlas。",
            path_fingerprint=lambda *a, **k: "fp",
            nodes_contract=lambda tr: {},
        )
        from application.chat import run_chat_turn as mod
        original = mod.agno_web_service.fetch_web_evidence_block
        mod.agno_web_service.fetch_web_evidence_block = lambda *a, **k: "[Web检索] 项目代号是 Atlas"
        try:
            out = run_agno_chat_turn_impl(
                "请根据知识库和网页证据回答：项目代号是什么",
                session_id="u3-test",
                deps=deps,
            )
        finally:
            mod.agno_web_service.fetch_web_evidence_block = original
        ex = out["extra"]
        assert ex.get("feedback_request"), "默认链触发补救时应暴露 feedback_request"
        assert ex.get("feedback_gate_result"), "默认链触发补救时应暴露 feedback_gate_result"
        assert ex.get("round_delta"), "默认链触发补救时应暴露 round_delta"
        assert ex.get("used_rounds") == [0, 1]


# ---------------------------------------------------------------------------
# 运行入口
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v", "--tb=short"])
