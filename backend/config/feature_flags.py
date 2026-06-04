from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

FEATURE_FLAGS: dict[str, bool] = {
    "ENABLE_INGRESS_ROUTER_V2": True,        # P6 — 默认启用 Semantic Router
    "ENABLE_FAST_LANE_VIDEO": True,          # P7
    "ENABLE_FAST_LANE_DOCUMENT": True,       # P7
    "ENABLE_FAST_LANE_WEB": True,            # P7
    "ENABLE_FAST_LANE_KB": True,             # P7
    "ENABLE_FAST_LANE_GENERAL": True,        # P7
    "ENABLE_THREE_AGENT_AUTONOMY": True,     # P8 — 默认启用三强自治闭环
    "ENABLE_ASYNC_CONTROL_PLANE_V2": True,   # P9 — 默认启用统一 async control plane
    # §13 协作施工计划 — 默认启用（S11 灰度收口）
    "ENABLE_MAIN_PLAN_CACHE": True,         # S1 — ingress hints + 单次 pan
    "ENABLE_BUDGET_CLOCK_V2": True,         # S2 — BudgetClock 贯穿
    "ENABLE_DECISION_ARBITRATOR": True,       # S3 — mode 仲裁
    "ENABLE_FAST_LANE_GATE": True,            # S5 — session pending 拒 fast
    "ENABLE_CAPABILITY_FACT_VIDEO": True,     # S4b — 视频 Capability 契约
    "ENABLE_CAPABILITY_FACT_WEB": True,       # S6 — 网页 Capability 契约
    "ENABLE_CAPABILITY_FACT_DOCUMENT": True,  # S7 — 文档 Capability 契约
    "ENABLE_CAPABILITY_FACT_KB": True,        # S6b — KB Capability 契约
    "ENABLE_DRAFT_ANSWER_V2": True,           # S9 — 后台 final_answer 草稿链
    "ENABLE_TURN_CACHE": True,                # S8 — within-turn 幂等
    "ENABLE_TURN_STITCHER": True,             # S8 — 任务结果回灌
    "ENABLE_ANSWER_TEXT_POLISH": True,        # 用户可见回答 markdown 乱格式清理（保留 emoji）
    "ENABLE_COMPLEX_PENDING_KIND_V2": True,   # S7c — complex/multisource PendingKind
    # Quality gate / shared retrieval (doc §17)
    "ENABLE_COMPLEXITY_POLICY": True,
    "ENABLE_QUALITY_GATE": True,
    "ENABLE_SHARED_RETRIEVAL": True,
    "ENABLE_KB_SUFFICIENCY_GATE": True,
    "ENABLE_APPROVAL_GATE_V1": True,
    # Turn exit gate — shadow off by default; gate always single-writes canonical exit.
    "ENABLE_TURN_EXIT_GATE_SHADOW": False,
    # RAG: 结构化切块实验开关（与 EMBEDDING_ENABLED 无关）
    "ENABLE_STRUCTURE_CHUNKING": False,
}

LANE_FAST_FLAG: dict[str, str] = {
    "video": "ENABLE_FAST_LANE_VIDEO",
    "document": "ENABLE_FAST_LANE_DOCUMENT",
    "web": "ENABLE_FAST_LANE_WEB",
    "kb": "ENABLE_FAST_LANE_KB",
    "general": "ENABLE_FAST_LANE_GENERAL",
}


def is_enabled(flag: str) -> bool:
    """Return True if the named feature flag is enabled."""
    return bool(FEATURE_FLAGS.get(flag, False))


def ingress_router_active() -> bool:
    """True when ingress router v2 should drive lane/mode selection at runtime."""
    return is_enabled("ENABLE_INGRESS_ROUTER_V2")


def fast_lane_active(lane: str) -> bool:
    """True when ingress router and the lane-specific fast path flag are both on."""
    flag = LANE_FAST_FLAG.get(lane)
    if not flag:
        return False
    return ingress_router_active() and is_enabled(flag)


def three_agent_autonomy_active() -> bool:
    """True when complex Main→Middle→Answer should run the autonomy feedback loop."""
    return is_enabled("ENABLE_THREE_AGENT_AUTONOMY")


def async_control_plane_active() -> bool:
    """True when video/web heavy tasks should use the unified task plane."""
    return is_enabled("ENABLE_ASYNC_CONTROL_PLANE_V2")


def main_plan_cache_active() -> bool:
    """True when ingress defers MainAgent.pan to run_chat_turn (§6.1)."""
    return is_enabled("ENABLE_MAIN_PLAN_CACHE") and ingress_router_active()


def budget_clock_v2_active() -> bool:
    """True when BudgetClock should drive turn-level SLA (§6.2)."""
    return is_enabled("ENABLE_BUDGET_CLOCK_V2") and ingress_router_active()


def capability_fact_video_active() -> bool:
    """True when video capability returns contract facts instead of legacy queued semantics."""
    return is_enabled("ENABLE_CAPABILITY_FACT_VIDEO")


def capability_fact_web_active() -> bool:
    """True when web capability returns contract facts (§8 / S6)."""
    return is_enabled("ENABLE_CAPABILITY_FACT_WEB")


def capability_fact_kb_active() -> bool:
    """True when KB capability returns contract facts (§7.4 / S6b)."""
    return is_enabled("ENABLE_CAPABILITY_FACT_KB")


def capability_fact_document_active() -> bool:
    """True when document capability returns contract facts (§9 / S7)."""
    return is_enabled("ENABLE_CAPABILITY_FACT_DOCUMENT")


def decision_arbitrator_active() -> bool:
    """True when mode demotion runs through decision_arbitrator (§5.6)."""
    return is_enabled("ENABLE_DECISION_ARBITRATOR") and ingress_router_active()


def complex_pending_kind_active() -> bool:
    """True when complex/multisource paths emit PendingKind on responses (§7.6 / S7c)."""
    return is_enabled("ENABLE_COMPLEX_PENDING_KIND_V2")


def complexity_policy_active() -> bool:
    return is_enabled("ENABLE_COMPLEXITY_POLICY") and ingress_router_active()


def quality_gate_active() -> bool:
    return is_enabled("ENABLE_QUALITY_GATE") and ingress_router_active()


def shared_retrieval_active() -> bool:
    return is_enabled("ENABLE_SHARED_RETRIEVAL") and ingress_router_active()


def kb_sufficiency_gate_active() -> bool:
    return is_enabled("ENABLE_KB_SUFFICIENCY_GATE") and ingress_router_active()


def approval_gate_active() -> bool:
    return is_enabled("ENABLE_APPROVAL_GATE_V1")


def _flag_on(flags: dict[str, bool], name: str) -> bool:
    return bool(flags.get(name, False))


def validate_flag_combination(flags: dict[str, bool] | None = None) -> list[str]:
    """Return validation errors for illegal flag combinations (§10.4).

    Empty list means the combination is valid. Callers may log errors and fall
    back to safe defaults when violations are returned.
    """
    f = flags if flags is not None else FEATURE_FLAGS
    errors: list[str] = []

    def on(name: str) -> bool:
        return _flag_on(f, name)

    if on("ENABLE_MAIN_PLAN_CACHE") and not on("ENABLE_INGRESS_ROUTER_V2"):
        errors.append("ENABLE_MAIN_PLAN_CACHE requires ENABLE_INGRESS_ROUTER_V2")

    if on("ENABLE_BUDGET_CLOCK_V2") and not on("ENABLE_INGRESS_ROUTER_V2"):
        errors.append("ENABLE_BUDGET_CLOCK_V2 requires ENABLE_INGRESS_ROUTER_V2")

    if on("ENABLE_DECISION_ARBITRATOR") and not on("ENABLE_BUDGET_CLOCK_V2"):
        errors.append("ENABLE_DECISION_ARBITRATOR requires ENABLE_BUDGET_CLOCK_V2")

    capability_fact_flags = (
        "ENABLE_CAPABILITY_FACT_VIDEO",
        "ENABLE_CAPABILITY_FACT_WEB",
        "ENABLE_CAPABILITY_FACT_DOCUMENT",
        "ENABLE_CAPABILITY_FACT_KB",
    )
    for cap_flag in capability_fact_flags:
        if on(cap_flag) and not on("ENABLE_DECISION_ARBITRATOR"):
            errors.append(f"{cap_flag} requires ENABLE_DECISION_ARBITRATOR")

    if on("ENABLE_TURN_STITCHER") and not on("ENABLE_ASYNC_CONTROL_PLANE_V2"):
        errors.append("ENABLE_TURN_STITCHER requires ENABLE_ASYNC_CONTROL_PLANE_V2")

    return errors


def turn_exit_gate_shadow_active() -> bool:
    return is_enabled("ENABLE_TURN_EXIT_GATE_SHADOW")


def embed_on_commit_active() -> bool:
    """Commit 后是否写 rag_embeddings。唯一事实源：``EMBEDDING_ENABLED``（与检索共用）。"""
    from config.settings import settings

    return bool(settings.embedding_enabled)


def assert_valid_flag_combination(flags: dict[str, bool] | None = None) -> None:
    """Log ERROR and raise ValueError when flag combination is invalid."""
    errors = validate_flag_combination(flags)
    if not errors:
        return
    for msg in errors:
        logger.error("Invalid feature flag combination: %s", msg)
    raise ValueError("; ".join(errors))
