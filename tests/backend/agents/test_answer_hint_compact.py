from __future__ import annotations

from types import SimpleNamespace

from agents.answer_agent.answer_bundle_extra import huida_to_executor_hint


def test_knowledge_grounded_compact_hint_trims_verbose_bundle_fields() -> None:
    hp = SimpleNamespace(da_fengshi="zhijie", jiegou_mode="sections", baoshou_level=0.2)
    xiezuo_pan = SimpleNamespace(
        renwu_lei="analysis",
        allow_kb=True,
        allow_web=False,
        fengxian_yinzi=0.3,
        celue_tag="kb_led",
    )
    cailiao_pan = SimpleNamespace(
        gou=True,
        bukong_xinhao="ok",
        laiyuan_zhu="kb",
        kb_qiangdu=0.9,
        que_shenme="none",
        xia_yi_bu="zhi_da",
    )
    plan = SimpleNamespace(answer_composition="kb_led", force_skip_evidence=False)
    bundle = SimpleNamespace(
        kb_evidence_tier="strong",
        insufficiency_signal="ok",
        trace=[],
        material_sufficiency="sufficient",
        retrieved_chunks=[1, 2, 3, 4],
        temporary_materials=[],
        commit_results=[],
        failures=[],
        bundle_id="b1",
        plan_id="p1",
    )

    text = huida_to_executor_hint(
        hp,
        xiezuo_pan,
        cailiao_pan,
        plan,
        bundle,
        compact=True,
    )

    assert "[main]" in text
    assert "[middle]" in text
    assert "[answer]" in text
    assert "bundle_id=" not in text
    assert "plan_id=" not in text
    assert "[v15/bundle]" not in text
