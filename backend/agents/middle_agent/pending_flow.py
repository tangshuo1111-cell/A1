"""台账 G-005「v13_pending_flow」：V13 prepare/commit 生命周期（默认由 `invoke_tail_flow` 调用）。

prepare → PendingKnowledgeItem；commit → 入库。trace / blocked_failures / knowledge_block
由调用方传入并在本阶段就地更新。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from agents.main_agent import AgnoCollaborationPlan
from services.capabilities.knowledge import pending_ingestion_service as _pending_svc
from services.capabilities.knowledge.pending_service import (
    SOURCE_TYPE_LOCAL_VIDEO,
    SOURCE_TYPE_TEXT,
    SOURCE_TYPE_TEXT_FILE,
    SOURCE_TYPE_WEB_URL,
    SOURCE_TYPE_WEB_VIDEO,
)

from .material_policy import _is_tool_allowed

logger = logging.getLogger("light_maqa")


@dataclass
class V13PhaseOutcome:
    knowledge_block: str | None
    pending_item_obj: Any | None
    v13_commit_result_obj: Any | None
    v13_material_status: str
    v13_source_type: str
    v13_used_pending_text: bool


def run_v13_prepare_commit_phase(
    *,
    plan: AgnoCollaborationPlan,
    inputs: dict[str, Any],
    msg: str,
    session_id: str,
    knowledge_block: str | None,
    lines: list[str],
    blocked_failures: list[dict[str, Any]],
    save_requested: bool,
    web_video_pending_early: Any | None,
    document_pending_early: Any | None,
    early_web_video_url_normalized: str,
) -> V13PhaseOutcome:
    v13_commit_result_obj = None
    v13_material_status = ""
    v13_source_type = ""
    v13_used_pending_text = False

    prepare_intent = getattr(plan, "v13_prepare_intent", None)
    commit_intent = getattr(plan, "v13_commit_intent", False)

    pending_item_obj = web_video_pending_early or document_pending_early
    kb = knowledge_block

    if prepare_intent is not None:
        _ptype = getattr(prepare_intent, "source_type", "text")
        _prepare_tool_name = (
            "prepare_file"
            if _ptype == SOURCE_TYPE_TEXT_FILE
            else f"prepare_{_ptype}"
        )
        _prepare_blocked = not _is_tool_allowed(plan, _prepare_tool_name)
        if _prepare_blocked:
            v13_material_status = "failed"
            blocked_failures.append({
                "tool": _prepare_tool_name,
                "reason": "not_allowed_by_plan",
                "recoverable": False,
            })
        if not _prepare_blocked:
            try:
                _ptype = prepare_intent.source_type
                v13_source_type = _ptype
                if _ptype == SOURCE_TYPE_TEXT:
                    _txt = str(inputs.get("v13_text_content") or msg)
                    pending_item_obj = _pending_svc.prepare_text_source(
                        _txt, session_id=session_id, title=inputs.get("v13_title") or ""
                    )
                elif _ptype == SOURCE_TYPE_TEXT_FILE:
                    if document_pending_early is not None:
                        pending_item_obj = document_pending_early
                        lines.append("v13:middle:prepare_file=skip_duplicate_early_prepare")
                    else:
                        _file_path = prepare_intent.raw_source
                        _file_content = inputs.get("v13_file_content")
                        pending_item_obj = _pending_svc.prepare_file_source(
                            _file_path, session_id=session_id, file_content=_file_content
                        )
                elif _ptype == SOURCE_TYPE_WEB_URL:
                    if document_pending_early is not None:
                        pending_item_obj = document_pending_early
                        lines.append("v13:middle:prepare_web_url=skip_duplicate_early_prepare")
                    else:
                        _url = prepare_intent.raw_source
                        pending_item_obj = _pending_svc.prepare_web_url_source(
                            _url, session_id=session_id
                        )
                elif _ptype == SOURCE_TYPE_LOCAL_VIDEO:
                    _mp4_path = prepare_intent.raw_source
                    try:
                        pending_item_obj = _pending_svc.prepare_local_video_source(
                            _mp4_path,
                            session_id=session_id,
                        )
                    except (OSError, ValueError, RuntimeError) as _local_video_e:
                        logger.warning("v16 local_video tool failed: %s", _local_video_e)
                        lines.append(
                            f"v16:middle:local_video=failed err={type(_local_video_e).__name__}"
                        )

                elif _ptype == SOURCE_TYPE_WEB_VIDEO:
                    _intent_vu = str(prepare_intent.raw_source or "").strip()
                    _skip_dup = (
                        web_video_pending_early is not None
                        and bool(early_web_video_url_normalized)
                        and _intent_vu == early_web_video_url_normalized
                    )
                    if _skip_dup:
                        pending_item_obj = web_video_pending_early
                        lines.append("v13:middle:web_video_prepare=skip_duplicate_early_fetch")
                    else:
                        _video_url = prepare_intent.raw_source
                        try:
                            pending_item_obj = _pending_svc.prepare_web_video_source(
                                _video_url,
                                session_id=session_id,
                            )
                        except (OSError, ValueError, RuntimeError) as _vt_e:
                            logger.warning("v16 web_video tool failed: %s", _vt_e)
                            lines.append(
                                f"v13:middle:video_url_fetch=failed err={type(_vt_e).__name__}"
                            )

                if pending_item_obj is not None:
                    _item = pending_item_obj
                    if _item.extract_status == "ok" and _item.text:
                        v13_material_status = "pending"
                        v13_used_pending_text = True
                        if not kb:
                            kb = (
                                f"[临时材料-待保存] 来源「{_item.title}」"
                                f"（{_item.source_type}）：\n\n{_item.text[:3000]}"
                            )
                            lines.append(
                                f"v13:middle:prepare=ok status=pending "
                                f"source_type={_item.source_type} "
                                f"pending_id={_item.pending_id[:8]} "
                                f"parser={_item.parser_name}"
                            )
                    else:
                        v13_material_status = "failed"
                        lines.append(
                            f"v13:middle:prepare=failed error={_item.error_code} "
                            f"source_type={_item.source_type}"
                        )
            except (OSError, ValueError, RuntimeError, TypeError) as _e:
                logger.warning("v13 prepare failed: %s", _e)
                lines.append(f"v13:middle:prepare=exception err={type(_e).__name__}")
                v13_material_status = "failed"

    if prepare_intent is None and pending_item_obj is not None:
        _it0 = pending_item_obj
        _ok_text = getattr(_it0, "extract_status", "") == "ok" and bool(
            (getattr(_it0, "text", "") or "").strip(),
        )
        if _ok_text:
            if not v13_material_status:
                v13_material_status = "pending"
            v13_used_pending_text = True
            if not v13_source_type and hasattr(_it0, "source_type"):
                v13_source_type = getattr(_it0, "source_type", "") or ""
            if not kb:
                kb = (
                    f"[临时材料-待保存] 来源「{getattr(_it0, 'title', '')}」"
                    f"（{getattr(_it0, 'source_type', '')}）：\n\n"
                    f"{(getattr(_it0, 'text', '') or '')[:3000]}"
                )
                lines.append(
                    f"v13:middle:prepare=ok status=pending early_web_video "
                    f"pending_id={getattr(_it0, 'pending_id', '')[:8]}"
                )

    if commit_intent or save_requested:
        _commit_blocked = not _is_tool_allowed(plan, "commit_pending")
        if _commit_blocked:
            v13_material_status = "failed"
            blocked_failures.append({
                "tool": "commit_pending",
                "reason": "not_allowed_by_plan",
                "recoverable": False,
            })
        if not _commit_blocked:
            try:
                _commit_all_flag = "全部" in msg or "all" in msg.lower()
                if _commit_all_flag:
                    _results = _pending_svc.commit_pending_by_session(session_id)
                    v13_commit_result_obj = _results[0] if _results else None
                    _ok_count = sum(1 for r in _results if r.success)
                    lines.append(
                        f"v13:middle:commit=batch ok={_ok_count}/{len(_results)} "
                        f"session={session_id[:8]}"
                    )
                else:
                    v13_commit_result_obj = _pending_svc.commit_most_recent_pending(session_id)
                    _cr = v13_commit_result_obj
                    if _cr.success:
                        v13_material_status = "committed"
                        v13_source_type = _cr.source_type
                        lines.append(
                            f"v13:middle:commit=ok source_id={_cr.source_id} "
                            f"chunks={_cr.chunk_count} title={_cr.title[:30]}"
                        )
                    else:
                        v13_material_status = "failed"
                        lines.append(
                            f"v13:middle:commit=failed error={_cr.error_code}"
                        )
            except (OSError, ValueError, RuntimeError, TypeError) as _e:
                logger.warning("v13 commit failed: %s", _e)
                lines.append(f"v13:middle:commit=exception err={type(_e).__name__}")
                v13_material_status = "failed"

    return V13PhaseOutcome(
        knowledge_block=kb,
        pending_item_obj=pending_item_obj,
        v13_commit_result_obj=v13_commit_result_obj,
        v13_material_status=v13_material_status,
        v13_source_type=v13_source_type,
        v13_used_pending_text=v13_used_pending_text,
    )
