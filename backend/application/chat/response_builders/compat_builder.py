"""Compatibility field preservation helpers."""

from __future__ import annotations

from typing import Any

from application.chat.field_owners import CANONICAL_EXTRA_KEYS


def merge_compat_fields(
    canonical_extra: dict[str, Any],
    source_extra: dict[str, Any],
) -> dict[str, Any]:
    merged = dict(canonical_extra)
    for key, value in source_extra.items():
        if key in CANONICAL_EXTRA_KEYS:
            continue
        merged[key] = value
    return merged
