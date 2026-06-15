from __future__ import annotations

from typing import Any

DEFAULT_COMPLEX_PATH = "agno_basic"
_INLINE_DOCUMENT_MARKER = "[inline_document]"


def _has_inline_document_material(bundle: Any) -> bool:
    temps = list(getattr(bundle, "temporary_materials", []) or [])
    return any(str(item).startswith(_INLINE_DOCUMENT_MARKER) for item in temps)


def resolve_complex_primary_path(bundle: Any) -> str:
    """Single source for complex-path labels derived from consumed material."""
    if _has_inline_document_material(bundle):
        return "document_complex"

    has_kb = bool((getattr(bundle, "knowledge_block", None) or "").strip())
    if not has_kb:
        has_kb = bool(list(getattr(bundle, "retrieved_chunks", []) or []))
    if not has_kb:
        kb_level = str(getattr(bundle, "kb_sufficiency_level", "") or "").strip().lower()
        has_kb = kb_level not in {"", "none"}
    has_web = bool((getattr(bundle, "web_block", None) or "").strip())
    if has_kb and has_web:
        return "agno_basic_v2_kb_v3_web"
    if has_kb:
        return "agno_basic_v2_kb"
    if has_web:
        return "agno_basic_v3_web"
    return DEFAULT_COMPLEX_PATH
