"""Web lane fast path implementation (Round 1)."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from application.chat.executors.fast_lanes import fast_common, fast_llm
from application.chat.exit_signals import set_pending_kind_signal
from application.chat.pending_kind import PendingKind


def run_web_fast_path(
    *,
    message: str,
    context_block: str | None,
    clock,
) -> tuple[str, dict[str, Any]] | None:
    from application.chat.decision_arbitrator import arbitrate_mode
    from application.ingress.lane_decision_schema import LaneDecision
    from services.capabilities.web import web_orchestration_service as agno_web_service

    budget_clock = clock
    url_match = re.search(r"https?://[^\s]+", message or "", flags=re.IGNORECASE)
    url = url_match.group(0) if url_match else ""
    if url:
        fact, advice = agno_web_service.probe_web_capability(
            url,
            clock=budget_clock,
        )
        if advice.suggested_mode == "demote_to_async":
            ingress = LaneDecision(
                lane="web",
                mode="fast",
                router_source="rule",
                router_confidence=0.9,
                router_decision_ms=0,
            )
            decided_mode, decided_reason = arbitrate_mode(
                session_pending=PendingKind.NONE,
                ingress=ingress,
                main_plan=None,
                capability_advice=advice,
                clock=budget_clock,
            )
            host = (urlparse(url).netloc or url).strip()
            extra: dict[str, Any] = {
                "fast_path": "web_fast_background_hint",
                "lane": "web",
                "mode": "fast",
                "capabilities_called": ["capability.web.probe"],
                "fast_exit_reason": "web_dynamic_required",
                "capability_advice": advice,
                "capability_fact": fact,
                "arbitrator.decided_mode": decided_mode,
                "arbitrator.decided_reason": decided_reason,
            }
            if decided_mode == "complex":
                return None
            if decided_mode == "async":
                set_pending_kind_signal(extra, PendingKind.FAST_PENDING.value)
                extra["fast_exit_reason"] = "web_fast_pending"
            answer = (
                f"这个网页静态抓取不足，已进入后台处理建议：{host}。"
                f"原因：{advice.reason or 'dynamic_required'}。"
            )
            return answer, extra

    material = agno_web_service.fetch_web_fast_material(message, max_results=2)
    if not (material or "").strip():
        return None
    body_text = fast_common._extract_page_body_from_material(material)
    material_sources = agno_web_service.detect_web_fast_material_sources(material)
    if fast_common._wants_full_web_text(message) and body_text:
        return body_text, {
            "fast_path": "web_fast_fulltext",
            "lane": "web",
            "mode": "fast",
            "web_search_used": material_sources.get("web_supplement_source") == "search",
            "web_evidence_chars": len(material),
            "web_output_mode": "fulltext",
            **material_sources,
            "capabilities_called": ["capability.web.static_fetch"],
            "fast_exit_reason": "web_static_fetch_fulltext",
        }
    answer_text = fast_llm.summarize_fast_material(
        lane="web", message=message, material=material, context_block=context_block
    )
    return answer_text, {
        "fast_path": "web_fast",
        "lane": "web",
        "mode": "fast",
        "web_search_used": True,
        "web_evidence_chars": len(material),
        **material_sources,
        "capabilities_called": ["capability.web.static_fetch"],
        "fast_exit_reason": "web_static_fetch_answer",
    }
