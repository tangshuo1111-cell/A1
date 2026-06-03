from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RouterPolicy:
    rule_accept_threshold: float = 0.85
    low_confidence_threshold: float = 0.60


ROUTER_POLICY = RouterPolicy()
