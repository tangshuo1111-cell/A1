"""Canonical HTTP field ownership (Round 9).

Each public field has exactly one writer module for the final response shape.
Intermediate candidates in executors/gates are overwritten at exit assembly.
"""

from __future__ import annotations

# Top-level ChatTurnResult keys and their final writer (module basename).
TOP_LEVEL_FIELD_OWNERS: dict[str, str] = {
    "task_status": "turn_response_builder",
    "primary_path": "turn_response_builder",
    "workflow_elapsed_ms": "turn_response_builder",
    "answer_type": "turn_response_builder",
    "task_id": "turn_response_builder",
    "ok": "turn_response_builder",
    "answer": "turn_response_builder",
    "pipeline_ok": "turn_response_builder",
}

# extra.* keys owned at exit assembly (decision / material lifecycle).
EXTRA_FIELD_OWNERS: dict[str, str] = {
    "mode": "turn_response_builder",
    "primary_path": "turn_response_builder",
    "router_lane": "turn_response_builder",
    "task_status": "turn_response_builder",
    "pending_kind": "turn_response_builder",
    "material_sufficiency": "turn_response_builder",
    "executor_profile": "turn_response_builder",
    "quality_gate": "turn_response_builder",
    "exit": "turn_response_builder",
}

CANONICAL_TOP_LEVEL_KEYS: frozenset[str] = frozenset(TOP_LEVEL_FIELD_OWNERS)
CANONICAL_EXTRA_KEYS: frozenset[str] = frozenset(EXTRA_FIELD_OWNERS)
