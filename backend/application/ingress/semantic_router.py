from __future__ import annotations

import time
from typing import Any, cast

from agents.main_agent import MainAgent
from application.chat.budget_clock import BudgetClock
from application.chat.complexity_policy import (
    STRONG_COMPLEX_REASON_CODES,
    evaluate_complex_candidate,
)
from config.feature_flags import is_enabled
from config.router_policy import ROUTER_POLICY

from .lane_decision_schema import LaneDecision, LaneName, ModeName, RouterSourceName
from .lane_selector import select_lane
from .main_plan_hints import MainPlanHints
from .mode_selector import select_mode
from .request_classifier import RequestSignals, classify_request
from .route_shadow import attach_route_shadow, should_skip_main_agent_escalation


def _lane_from_main_plan(
    plan: Any,
    *,
    use_knowledge: bool,
    has_document_payload: bool,
    signals: RequestSignals | None = None,
) -> str:
    if getattr(plan, "video_url", None):
        return "video"
    # KI-V1-001：显式网页读取意图且无文件 payload 时，MainAgent 若误标 text/text_file
    # 仍保持 web lane，避免 web↔document 漂移（诚实性规则不变）。
    if (
        signals is not None
        and signals.has_web_url
        and signals.has_web_intent
        and not has_document_payload
    ):
        prepare_intent = getattr(plan, "v13_prepare_intent", None)
        source_type = str(getattr(prepare_intent, "source_type", "") or "")
        if source_type in {"", "text", "text_file"}:
            return "web"
    if has_document_payload:
        return "document"
    prepare_intent = getattr(plan, "v13_prepare_intent", None)
    source_type = str(getattr(prepare_intent, "source_type", "") or "")
    if source_type in {"text", "text_file"}:
        return "document"
    answer_channel = str(getattr(getattr(plan, "decision", None), "answer_channel", "") or "")
    if answer_channel == "external":
        return "web"
    if use_knowledge or answer_channel in {"kb", "mixed"} or bool(getattr(getattr(plan, "decision", None), "need_rag", False)):
        return "kb"
    return "general"


def _mode_from_main_plan(plan: Any, *, default_mode: str) -> str:
    if str(getattr(plan, "job_type", "") or "") == "multi_source_compare":
        return "complex"
    max_rounds = int(getattr(plan, "max_rounds", 0) or 0)
    if max_rounds > 1:
        return "complex"
    return default_mode


def route_chat_request(
    *,
    message: str,
    session_id: str | None,
    request_id: str | None,
    use_knowledge: bool,
    v13_file_content: str | bytes | None,
    v13_text_content: str | None,
    attachments: list[dict[str, Any]] | None = None,
    main_agent: MainAgent | None = None,
    context_snippet: str = "",
    clock: BudgetClock,
) -> LaneDecision:
    started = time.perf_counter()
    signals = classify_request(
        message=message,
        use_knowledge=use_knowledge,
        v13_file_content=v13_file_content,
        v13_text_content=v13_text_content,
        attachments=attachments,
    )
    lane, lane_confidence = select_lane(signals)
    complex_signal = evaluate_complex_candidate(message)
    mode, mode_confidence = select_mode(
        lane=lane,
        signals=signals,
        message=message,
        complex_candidate=complex_signal.complex_candidate,
        complex_reason_codes=tuple(complex_signal.reason_codes),
    )
    confidence = min(lane_confidence, mode_confidence)
    if (
        mode == "complex"
        and complex_signal.complex_candidate
        and set(complex_signal.reason_codes) & STRONG_COMPLEX_REASON_CODES
    ):
        confidence = max(confidence, 0.88)
    router_source = "rule"
    fallback = False
    escalated = False
    rule_lane, rule_mode = lane, mode

    cached_hints: MainPlanHints | None = None

    if confidence < ROUTER_POLICY.low_confidence_threshold and main_agent is not None:
        if should_skip_main_agent_escalation(
            rule_lane=rule_lane,
            rule_mode=rule_mode,
            message=message,
            signals=signals,
            complex_reason_codes=tuple(complex_signal.reason_codes),
        ):
            router_source = "light_classifier"
            confidence = max(confidence, 0.78)
            fallback = False
            escalated = False
        elif is_enabled("ENABLE_MAIN_PLAN_CACHE"):
            cached_hints = MainPlanHints(router_reason="low_confidence_deferred_to_main")
            router_source = "main_agent"
            confidence = 0.62 if lane == "general" else 0.78
            fallback = True
            escalated = True
        else:
            from application.chat.chat_contracts import coerce_main_agent_result

            main_result = coerce_main_agent_result(
                main_agent.pan(
                    message,
                    session_id=session_id,
                    http_use_knowledge=use_knowledge,
                    context_snippet=context_snippet,
                    clock=clock,
                )
            )
            plan = main_result.plan
            lane = _lane_from_main_plan(
                plan,
                use_knowledge=use_knowledge,
                has_document_payload=signals.has_document_payload,
                signals=signals,
            )
            mode = _mode_from_main_plan(plan, default_mode=mode)
            router_source = "main_agent"
            confidence = 0.62 if lane == "general" else 0.78
            fallback = True
            escalated = True
    elif confidence < ROUTER_POLICY.rule_accept_threshold:
        router_source = "light_classifier"
        confidence = max(confidence, 0.72)

    decision = LaneDecision(
        request_id=str(request_id or ""),
        session_id=str(session_id or ""),
        lane=cast(LaneName, lane),
        mode=cast(ModeName, mode),
        router_source=cast(RouterSourceName, router_source),
        router_confidence=round(confidence, 4),
        router_fallback=fallback,
        router_decision_ms=max(0, int((time.perf_counter() - started) * 1000)),
        escalated_to_main_agent=escalated,
        cached_main_hints=cached_hints,
        complex_candidate=complex_signal.complex_candidate,
        complex_triggers=list(complex_signal.triggers),
        complex_reason_codes=list(complex_signal.reason_codes),
    )
    return attach_route_shadow(
        decision,
        rule_lane=rule_lane,
        rule_mode=rule_mode,
        message=message,
        signals=signals,
    )
