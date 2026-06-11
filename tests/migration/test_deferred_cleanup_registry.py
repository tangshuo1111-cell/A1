"""Deferred cleanup items — post-R15 backlog (module size only)."""

from __future__ import annotations

import json
from pathlib import Path

REGISTRY = Path(__file__).with_name("deferred_cleanup_registry.json")


def test_deferred_cleanup_registry_module_size_only() -> None:
    data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    ids = {item["id"] for item in data["items"]}
    assert ids == {
        "module_size_turn_orchestrator",
        "module_size_complex_executor",
        "module_size_fast_executor",
        "module_size_fast_executor_general_attempts",
    }
    for item in data["items"]:
        assert str(item.get("retire_by_round", "")).startswith(("R", "post-R"))
