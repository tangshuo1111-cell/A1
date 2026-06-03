"""Validate §13 feature-flag combinations when all S1–S10 flags are enabled."""
from __future__ import annotations

from config.feature_flags import FEATURE_FLAGS, assert_valid_flag_combination


def test_validate_flag_combination_all_s13_flags_enabled() -> None:
    flags = dict(FEATURE_FLAGS)
    flags.update(
        {
            "ENABLE_MAIN_PLAN_CACHE": True,
            "ENABLE_BUDGET_CLOCK_V2": True,
            "ENABLE_DECISION_ARBITRATOR": True,
            "ENABLE_FAST_LANE_GATE": True,
            "ENABLE_CAPABILITY_FACT_VIDEO": True,
            "ENABLE_CAPABILITY_FACT_WEB": True,
            "ENABLE_CAPABILITY_FACT_DOCUMENT": True,
            "ENABLE_CAPABILITY_FACT_KB": True,
            "ENABLE_DRAFT_ANSWER_V2": True,
            "ENABLE_TURN_CACHE": True,
            "ENABLE_TURN_STITCHER": True,
            "ENABLE_COMPLEX_PENDING_KIND_V2": True,
        }
    )
    assert_valid_flag_combination(flags)
