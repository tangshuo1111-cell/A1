"""Unit tests for complexity_policy and quality_gate."""
from __future__ import annotations

from application.chat.chat_contracts import (
    KbSufficiencyResult,
    MaterialGateFacts,
    RetrievalSnapshot,
)
from application.chat.complexity_policy import evaluate_complex_candidate
from application.chat.quality_gate import evaluate_quality_gate
from config.feature_flags import FEATURE_FLAGS
from services.capabilities.knowledge.kb_sufficiency import evaluate_kb_sufficiency, tier_from_score


class TestComplexityPolicy:
    def test_comparison_is_complex_candidate(self):
        sig = evaluate_complex_candidate("请对比方案A和方案B的优缺点")
        assert sig.complex_candidate is True
        assert "comparison" in sig.reason_codes

    def test_simple_explain_not_complex(self):
        sig = evaluate_complex_candidate("CORS 是什么")
        assert sig.complex_candidate is False

    def test_decision_support_angles_is_complex_candidate(self):
        sig = evaluate_complex_candidate("请从职业成长、风险、现金流、安全边际三个角度帮我做决策。")
        assert sig.complex_candidate is True
        assert "decision_tradeoff" in sig.reason_codes

    def test_diagnostic_explanations_is_complex_candidate(self):
        sig = evaluate_complex_candidate("请列出5种可能解释，并说明每种解释对应的验证方法。")
        assert sig.complex_candidate is True
        assert "diagnostic_reasoning" in sig.reason_codes

    def test_two_perspective_is_multi_dimension(self):
        sig = evaluate_complex_candidate(
            "请站在产品经理和工程师两个视角，分别说明如何验收一个 AI 问答系统的默认主路径是否生效。"
        )
        assert sig.complex_candidate is True
        assert "multi_dimension" in sig.reason_codes
        sig = evaluate_complex_candidate(
            "假设你要设计一个多材料 AI 问答系统，请说明路由、质量门和统一出口应如何分工，并解释为什么。"
        )
        assert sig.complex_candidate is True
        assert "solution_design" in sig.reason_codes

    def test_sandbox_upgrade_01_is_candidate(self):
        sig = evaluate_complex_candidate(
            "这是一个需要多步推理的问题：如果系统默认先 fast 再 quality gate 升级 complex，"
            "请分析 partial 交付对用户体验的影响，并给出三条改进建议。"
        )
        assert sig.complex_candidate is True
        assert "multi_step" in sig.reason_codes or "decision_tradeoff" in sig.reason_codes


class TestComplexTaskScope:
    def test_execution_complex_mode(self):
        from application.chat.complexity_policy import is_complex_task_scope

        assert is_complex_task_scope(mode="complex", executor_profile="complex") is True

    def test_async_profile(self):
        from application.chat.complexity_policy import is_complex_task_scope

        assert is_complex_task_scope(mode="async", executor_profile="async") is True

    def test_complex_candidate_strong_codes(self):
        from application.chat.complexity_policy import is_complex_task_scope

        assert is_complex_task_scope(
            mode="fast",
            executor_profile="fast",
            complex_candidate=True,
            complex_reason_codes=("solution_design",),
        ) is True

    def test_weak_only_not_in_scope(self):
        from application.chat.complexity_policy import is_complex_task_scope

        assert is_complex_task_scope(
            mode="fast",
            complex_candidate=True,
            complex_reason_codes=("multi_analysis",),
        ) is False


class TestKbSufficiency:
    def test_simple_adequate_with_one_hit(self):
        snap = RetrievalSnapshot(hits=1, top_score=0.5, evidence_tier="usable", rag_miss=False)
        result = evaluate_kb_sufficiency(snap, complex_candidate=False)
        assert result.adequate is True
        assert result.level == "adequate_simple"

    def test_complex_insufficient_with_weak_evidence(self):
        snap = RetrievalSnapshot(hits=2, top_score=0.4, evidence_tier="usable", rag_miss=False)
        result = evaluate_kb_sufficiency(snap, complex_candidate=True)
        assert result.adequate is False
        assert "kb_hits_below_complex" in result.reason_codes or "kb_tier_below_complex" in result.reason_codes

    def test_complex_adequate_with_two_strong_hits(self):
        snap = RetrievalSnapshot(hits=2, top_score=0.76, evidence_tier="strong", rag_miss=False)
        result = evaluate_kb_sufficiency(snap, complex_candidate=True)
        assert result.adequate is True
        assert result.level == "adequate_complex"

    def test_tier_from_score(self):
        assert tier_from_score(hits=0, top_score=0.0) == "none"
        assert tier_from_score(hits=2, top_score=0.7) == "strong"


class TestQualityGate:
    def test_complex_fast_shallow_upgrades(self):
        gate = evaluate_quality_gate(
            executor_profile="fast",
            complex_candidate=True,
            answer_text="简短回答。",
            complex_reason_codes=("comparison",),
        )
        assert gate.pass_ is False
        assert gate.upgrade_profile is True
        assert "answer_too_shallow" in gate.reason_codes

    def test_complex_fast_good_passes(self):
        text = (
            "相比方案A，方案B在成本上更优，但在扩展性方面较弱。"
            "从实施周期看，A更适合短期上线，B更适合长期演进。"
            "1. 成本：B更低\n2. 扩展：A更好\n3. 风险：B需补监控\n"
            "总结：若重视交付速度选A，若重视长期架构选B。"
        )
        assert len(text) >= 80
        gate = evaluate_quality_gate(
            executor_profile="fast",
            complex_candidate=True,
            answer_text=text,
            kb_sufficiency=KbSufficiencyResult(adequate=True, level="adequate_complex"),
            complex_reason_codes=("comparison",),
        )
        assert gate.pass_ is True
        assert gate.upgrade_profile is False

    def test_kb_insufficient_triggers_upgrade_on_fast(self):
        gate = evaluate_quality_gate(
            executor_profile="fast",
            complex_candidate=True,
            answer_text="这是一段足够长的回答，包含对比：A相比B更稳妥，并从多个角度展开说明。",
            kb_sufficiency=KbSufficiencyResult(
                adequate=False,
                level="insufficient",
                reason_codes=("kb_miss",),
            ),
            lane="kb",
            complex_reason_codes=("comparison",),
        )
        assert gate.upgrade_profile is True
        assert "kb_insufficient" in gate.reason_codes

    def test_decision_tradeoff_without_case_analysis_upgrades(self):
        text = "建议优先融资，同时控制成本。最终建议是尽快融资，但也要谨慎。"
        gate = evaluate_quality_gate(
            executor_profile="fast",
            complex_candidate=True,
            answer_text=text,
            complex_reason_codes=("decision_tradeoff", "multi_dimension"),
        )
        assert gate.upgrade_profile is True
        assert "case_analysis_missing" in gate.reason_codes

    def test_decision_tradeoff_with_case_analysis_still_upgrades_on_fast(self):
        text = (
            "分情况分析：\n"
            "1. 如果已有明确用户增长，就优先融资，争取把窗口期拉长。\n"
            "2. 如果增长停滞且团队臃肿，就先裁员，把现金流拉回安全区。\n"
            "3. 如果反馈积极但产品还不够聚焦，就继续打磨产品，但只保留一个核心场景。\n"
            "最终建议：优先融资，但必须同步做成本控制和单场景验证。"
        )
        gate = evaluate_quality_gate(
            executor_profile="fast",
            complex_candidate=True,
            answer_text=text,
            complex_reason_codes=("decision_tradeoff", "multi_dimension"),
        )
        assert gate.pass_ is False
        assert gate.upgrade_profile is True
        assert "deep_complex_requires_agent" in gate.reason_codes

    def test_decision_tradeoff_with_case_analysis_can_pass_in_complex(self):
        text = (
            "分情况分析：\n"
            "1. 如果已有明确用户增长，就优先融资，争取把窗口期拉长。\n"
            "2. 如果增长停滞且团队臃肿，就先裁员，把现金流拉回安全区。\n"
            "3. 如果反馈积极但产品还不够聚焦，就继续打磨产品，但只保留一个核心场景。\n"
            "最终建议：优先融资，但必须同步做成本控制和单场景验证。"
        )
        gate = evaluate_quality_gate(
            executor_profile="complex",
            complex_candidate=True,
            answer_text=text,
            complex_reason_codes=("decision_tradeoff", "multi_dimension"),
        )
        assert gate.pass_ is True

    def test_soft_limitations_do_not_force_second_round(self):
        text = (
            "这是一个完整回答。\n"
            "1. 先统一主链和事实源，避免多处各算一份状态。\n"
            "2. 再统一 shared retrieval 与 quality gate 的消费口径。\n"
            "最终建议：优先统一主链，再提升知识检索厚度。"
        )
        gate = evaluate_quality_gate(
            executor_profile="complex",
            complex_candidate=True,
            answer_text=text,
            limitations=["tool 失败：parallel_budget_zero", "首响预算不足，部分证据尚未补齐。"],
            complex_reason_codes=("multi_dimension",),
        )
        assert gate.pass_ is True
        assert gate.need_second_round is False

    def test_direct_fastpath_factless_limitation_is_soft(self):
        text = (
            "分情况分析：\n"
            "1. 如果还在验证需求阶段，就别急着加功能，先做用户访谈。\n"
            "2. 如果已有初步验证，就小步优化核心体验，不要大改架构。\n"
            "最终建议：先验证方向，再决定融资或裁员。"
        )
        gate = evaluate_quality_gate(
            executor_profile="complex",
            complex_candidate=True,
            answer_text=text,
            limitations=["本轮按直答快路径处理，未要求事实性证据。"],
            complex_reason_codes=("decision_tradeoff", "multi_dimension"),
        )
        assert gate.pass_ is True
        assert gate.need_second_round is False

    def test_plain_word_jieduan_does_not_count_as_truncation(self):
        text = "这一周要解决回答截断问题，但这段答案本身已经完整结束。"
        gate = evaluate_quality_gate(
            executor_profile="complex",
            complex_candidate=True,
            answer_text=text,
            complex_reason_codes=("solution_design",),
        )
        assert "answer_truncated" not in gate.reason_codes

    def test_complex_material_insufficient_triggers_second_round_and_need_more_material(self):
        gate = evaluate_quality_gate(
            executor_profile="complex",
            round_index=0,
            complex_candidate=True,
            answer_text=(
                "当前未从知识库检索到可用片段（retrieved_chunks 为空），"
                "无法基于知识库材料作答。"
            ),
            material_facts=MaterialGateFacts(
                material_sufficiency="insufficient",
                material_still_insufficient=True,
                try_rag_executed=True,
                has_web_evidence=False,
                allow_web=True,
            ),
            use_knowledge=True,
            retrieved_chunks_count=1,
        )
        assert gate.pass_ is False
        assert gate.need_second_round is True
        assert gate.need_more_material is True
        assert "material_insufficient" in gate.reason_codes
        assert "evidence_not_used" in gate.reason_codes

    def test_general_lane_refine_v2_narrows_material_need_more(self):
        saved = dict(FEATURE_FLAGS)
        try:
            FEATURE_FLAGS["ENABLE_COMPLEX_REFINE_V2"] = True
            gate = evaluate_quality_gate(
                executor_profile="complex",
                round_index=0,
                complex_candidate=True,
                answer_text="材料不足，无法确认。",
                limitations=["当前未从知识库检索到可用片段，也未获得可用的外部网页证据"],
                material_facts=MaterialGateFacts(
                    material_sufficiency="insufficient",
                    material_still_insufficient=True,
                    try_rag_executed=True,
                    has_web_evidence=False,
                    allow_web=True,
                ),
                lane="general",
                use_knowledge=False,
                retrieved_chunks_count=0,
                complex_reason_codes=("comparison", "multi_dimension"),
            )
            assert gate.pass_ is False
            assert gate.need_second_round is True
            assert gate.need_more_material is False
            assert "material_insufficient" not in gate.reason_codes
            assert "answer_too_shallow" in gate.reason_codes
        finally:
            FEATURE_FLAGS.clear()
            FEATURE_FLAGS.update(saved)
