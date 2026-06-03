"""Shared builders extracted from the large V15 unified main-chain suite."""

from __future__ import annotations


def make_plan(**kw):
    from agents.main_agent.schema import AgnoCollaborationPlan, MainXiezuoPan
    from schemas import MainDecision

    decision = MainDecision(
        answer_channel="zhijie",
        need_rag=kw.get("need_rag", False),
        task_id="test-task-001",
        router_source="main_agent_runtime",
    )
    xp = MainXiezuoPan(
        renwu_lei="zhijie",
        zhengju_need=kw.get("need_rag", False),
        allow_kb=kw.get("allow_kb", False),
        allow_web=False,
        fengxian_yinzi=0.1,
        celue_tag="test",
    )
    return AgnoCollaborationPlan(
        decision=decision,
        force_skip_evidence=kw.get("force_skip", False),
        web_supplement_mode="explicit_only",
        answer_composition="standard",
        xiezuo_pan=xp,
        needs_retrieval=kw.get("needs_retrieval", False),
        retrieval_strategy=kw.get("retrieval_strategy", "auto"),
        needs_pending=kw.get("needs_pending", False),
        pending_reference=kw.get("pending_reference", "none"),
        answer_mode=kw.get("answer_mode", "direct"),
        tools_allowed=kw.get("tools_allowed", ()),
    )


def make_bundle(**kw):
    from agents.middle_agent.schema import AgnoMaterialBundle, CailiaoPan

    cp = CailiaoPan(
        gou=kw.get("gou", True),
        kb_qiangdu=0.8,
        bukong_xinhao="ok",
        laiyuan_zhu="kb",
        use_kb=True,
        use_web=False,
        que_shenme="none",
        xia_yi_bu="zhi_da",
    )
    return AgnoMaterialBundle(
        knowledge_block=kw.get("knowledge_block", "测试材料"),
        web_block=None,
        trace=["v4:1_route:kb"],
        knowledge_adequate=True,
        material_still_insufficient=False,
        web_judgment_reason="no_web",
        kb_evidence_tier="strong",
        insufficiency_signal="ok",
        cailiao_pan=cp,
        retrieved_chunks=kw.get("retrieved_chunks", []),
        plan_id=kw.get("plan_id", "test-plan-001"),
        execution_status=kw.get("execution_status", "ok"),
        tool_calls=kw.get("tool_calls", []),
        temporary_materials=kw.get("temporary_materials", []),
        commit_results=kw.get("commit_results", []),
        failures=kw.get("failures", []),
        material_sufficiency=kw.get("material_sufficiency", "sufficient"),
    )
