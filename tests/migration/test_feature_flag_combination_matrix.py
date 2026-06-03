"""§10.4 flag combination matrix — illegal combos must be rejected."""
from __future__ import annotations

import pytest

from config.feature_flags import FEATURE_FLAGS, validate_flag_combination


def _flags(**overrides: bool) -> dict[str, bool]:
    merged = dict(FEATURE_FLAGS)
    merged.update(overrides)
    return merged


class TestFeatureFlagCombinationMatrix:
    def test_default_flags_are_valid(self):
        assert validate_flag_combination(FEATURE_FLAGS) == []

    @pytest.mark.parametrize(
        ("overrides", "fragment"),
        [
            (
                {"ENABLE_INGRESS_ROUTER_V2": False, "ENABLE_MAIN_PLAN_CACHE": True},
                "ENABLE_MAIN_PLAN_CACHE requires ENABLE_INGRESS_ROUTER_V2",
            ),
            (
                {"ENABLE_INGRESS_ROUTER_V2": False, "ENABLE_BUDGET_CLOCK_V2": True},
                "ENABLE_BUDGET_CLOCK_V2 requires ENABLE_INGRESS_ROUTER_V2",
            ),
            (
                {"ENABLE_DECISION_ARBITRATOR": True, "ENABLE_BUDGET_CLOCK_V2": False},
                "ENABLE_DECISION_ARBITRATOR requires ENABLE_BUDGET_CLOCK_V2",
            ),
            (
                {"ENABLE_CAPABILITY_FACT_VIDEO": True, "ENABLE_DECISION_ARBITRATOR": False},
                "ENABLE_CAPABILITY_FACT_VIDEO requires ENABLE_DECISION_ARBITRATOR",
            ),
            (
                {"ENABLE_CAPABILITY_FACT_WEB": True, "ENABLE_DECISION_ARBITRATOR": False},
                "ENABLE_CAPABILITY_FACT_WEB requires ENABLE_DECISION_ARBITRATOR",
            ),
            (
                {"ENABLE_CAPABILITY_FACT_DOCUMENT": True, "ENABLE_DECISION_ARBITRATOR": False},
                "ENABLE_CAPABILITY_FACT_DOCUMENT requires ENABLE_DECISION_ARBITRATOR",
            ),
            (
                {"ENABLE_CAPABILITY_FACT_KB": True, "ENABLE_DECISION_ARBITRATOR": False},
                "ENABLE_CAPABILITY_FACT_KB requires ENABLE_DECISION_ARBITRATOR",
            ),
            (
                {"ENABLE_TURN_STITCHER": True, "ENABLE_ASYNC_CONTROL_PLANE_V2": False},
                "ENABLE_TURN_STITCHER requires ENABLE_ASYNC_CONTROL_PLANE_V2",
            ),
        ],
    )
    def test_illegal_combinations(self, overrides: dict[str, bool], fragment: str):
        errors = validate_flag_combination(_flags(**overrides))
        assert any(fragment in err for err in errors), errors
