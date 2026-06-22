from __future__ import annotations

from typing import Any


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
    extra["mode"] = mode
    extra["executor_profile"] = executor_profile
    return extra
