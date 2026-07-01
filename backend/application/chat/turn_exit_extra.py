from __future__ import annotations

from typing import Any

from config.settings import settings


def build_common_exit_extra(
    *,
    extra_base: dict[str, Any] | None,
    ingress: Any | None,
    mode: str,
    executor_profile: str,
    progress_stage: str,
    elapsed_ms: int,
) -> dict[str, Any]:
    extra = dict(extra_base or {})
    extra["progress_stage"] = progress_stage
    extra["elapsed_ms"] = elapsed_ms
    extra["timing_total_ms"] = elapsed_ms
    if ingress is not None:
        extra["router_lane"] = getattr(ingress, "lane", "")
        from application.ingress.route_shadow import route_shadow_extra

        extra.update(route_shadow_extra(ingress))
    extra["runtime_mode"] = "fake_llm" if settings.fake_llm_enabled else "real_llm"
    extra["fake_llm_enabled"] = bool(settings.fake_llm_enabled)
    extra["fake_llm_source_conflict"] = bool(settings.fake_llm_source_conflict())
    extra["mode"] = mode
    extra["executor_profile"] = executor_profile
    return extra
