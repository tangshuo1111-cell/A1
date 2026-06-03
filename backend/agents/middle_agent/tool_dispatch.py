"""台账 G-005「tool_dispatch」：多工具逐步调度与 V16/V17 工具入口聚合。

历史文件名 `v17_tool_dispatch.py` 已废止；逻辑迁入本模块。
符号前缀 `_v17_*` / trace 键 `v17:*` 保留，避免行为与观测指纹漂移。
"""

from __future__ import annotations

import time
from typing import Any

from agents.source_analyst import SourceAnalystRuntime


class _V17ServiceToolResult:
    def __init__(self, **kwargs: Any) -> None:
        self.tool_name = kwargs.get("tool_name", "")
        self.status = kwargs.get("status", "failed")
        self.text = kwargs.get("text", "")
        self.metadata = kwargs.get("metadata", {})
        self.quality = kwargs.get("quality", {})
        self.error_code = kwargs.get("error_code", "")
        self.failure_reason = kwargs.get("failure_reason", "")
        self.pending_id = kwargs.get("pending_id", "")
        self.source_id = kwargs.get("source_id", "")
        self.retrieved_chunk_ids = kwargs.get("retrieved_chunk_ids", [])
        self.duration_ms = kwargs.get("duration_ms", 0.0)
        self.trace = kwargs.get("trace", [])

    def to_trace_dict(self) -> dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "status": self.status,
            "error_code": self.error_code,
            "failure_reason": self.failure_reason,
            "pending_id": self.pending_id,
            "source_id": self.source_id,
            "retrieved_chunk_ids": self.retrieved_chunk_ids,
            "text_length": len(self.text or ""),
            "metadata": self.metadata,
            "trace": self.trace[:10],
        }


def _call_v17_prepare_tool(tool_name: str, args: dict[str, Any], pending_svc: Any) -> _V17ServiceToolResult:
    session_id = str(args.get("session_id") or "v17-tool-audit")
    mapping = {
        "prepare_text": lambda: pending_svc.prepare_text_source(str(args.get("text", "")), session_id=session_id, title=str(args.get("title", ""))),
        "prepare_file": lambda: pending_svc.prepare_file_source(str(args.get("file_path", "")), session_id=session_id, file_content=args.get("file_content")),
        "prepare_document": lambda: pending_svc.prepare_document_source(str(args.get("file_path", "")), session_id=session_id, file_content=args.get("file_content")),
        "prepare_web_url": lambda: pending_svc.prepare_web_url_source(str(args.get("url", "")), session_id=session_id, fetch_method=str(args.get("fetch_method", "static")), cookie=str(args.get("cookie", ""))),
        "prepare_local_video": lambda: pending_svc.prepare_local_video_source(str(args.get("file_path", "")), session_id=session_id),
        "prepare_web_video": lambda: pending_svc.prepare_web_video_source(str(args.get("url", "")), session_id=session_id),
        "prepare_ocr": lambda: pending_svc.prepare_ocr_source(str(args.get("file_path", "")), session_id=session_id, estimated_cost=float(args.get("estimated_cost", 0.0))),
        "prepare_asr": lambda: pending_svc.prepare_asr_source(str(args.get("file_path", "")), session_id=session_id, duration_sec=float(args.get("duration_sec", 0.0)), estimated_cost=float(args.get("estimated_cost", 0.0))),
        "prepare_web_search": lambda: pending_svc.prepare_web_search_source(str(args.get("query", "")), session_id=session_id, provider_override=str(args.get("provider_override", ""))),
    }
    if tool_name not in mapping:
        return _V17ServiceToolResult(tool_name=tool_name, status="failed", error_code="tool_not_found", failure_reason=f"未支持的 prepare tool: {tool_name}")
    item = mapping[tool_name]()
    payload = getattr(item, "payload", None)
    text = getattr(payload, "text", "") if payload is not None else ""
    status = "success" if getattr(item, "extract_status", "") == "ok" else "failed"
    return _V17ServiceToolResult(
        tool_name=tool_name,
        status=status,
        text=text,
        pending_id=getattr(item, "pending_id", ""),
        source_id=getattr(payload, "source_id", "") if payload is not None else "",
        error_code=getattr(item, "error_code", "") if status != "success" else "",
        metadata={"parser_name": getattr(item, "parser_name", ""), "extract_status": getattr(item, "extract_status", "")},
        trace=[f"v17:prepare:{tool_name}:status={status}"],
    )


def _call_v17_commit_tool(args: dict[str, Any], pending_svc: Any) -> _V17ServiceToolResult:
    pending_id = str(args.get("pending_id") or "")
    if pending_id:
        r = pending_svc.commit_pending(pending_id)
    else:
        r = pending_svc.commit_most_recent_pending(str(args.get("session_id") or "v17-tool-audit"))
    return _V17ServiceToolResult(
        tool_name="commit_pending",
        status="success" if r.success else "failed",
        pending_id=r.pending_id,
        source_id=r.source_id,
        error_code=r.error_code,
        text=f"committed {r.source_id}" if r.success else "",
        metadata=r.to_trace_dict(),
        trace=["v17:commit_pending"],
    )


def _call_v17_retrieve_tool(args: dict[str, Any], retrieve_fn: Any) -> _V17ServiceToolResult:
    chunks, info = retrieve_fn(
        str(args.get("query", "")),
        top_k=int(args.get("top_k", 5)),
        strategy=str(args.get("strategy", "auto")),
        filters=args.get("filters") or None,
        embedding_enabled=args.get("embedding_enabled"),
    )
    ids = [getattr(c, "chunk_id", "") for c in chunks]
    text = "\n".join(c.to_context_line() if hasattr(c, "to_context_line") else str(c) for c in chunks)
    return _V17ServiceToolResult(
        tool_name="retrieve_knowledge",
        status="success" if chunks else "failed",
        text=text,
        source_id=str((args.get("filters") or {}).get("source_id", "")),
        retrieved_chunk_ids=ids,
        error_code="" if chunks else "no_match",
        metadata=info,
        trace=["v17:retrieve_knowledge"],
    )


def _dispatch_v17_tool(tool_name: str, args: dict[str, Any]) -> tuple[_V17ServiceToolResult, str]:
    from services.capabilities.knowledge import pending_ingestion_service as pending_svc
    from services.capabilities.knowledge.retrieve_service import retrieve_knowledge
    from tools.asr import asr_transcribe as _registered_asr  # noqa: F401
    from tools.asr import registry as asr_registry
    from tools.document import parse_docx as _registered_docx  # noqa: F401
    from tools.document import parse_excel as _registered_excel  # noqa: F401
    from tools.document import parse_pdf as _registered_pdf  # noqa: F401
    from tools.document import parse_text as _registered_text  # noqa: F401
    from tools.document import registry as doc_registry
    from tools.ocr import ocr_document as _registered_ocr  # noqa: F401
    from tools.ocr import registry as ocr_registry
    from tools.search import registry as search_registry
    from tools.search import web_search as _registered_search  # noqa: F401
    from tools.video import extract_local_video_subtitle as _registered_local_video  # noqa: F401
    from tools.video import extract_web_video_subtitle as _registered_web_video  # noqa: F401
    from tools.video import registry as video_registry
    from tools.web import fetch_dynamic_page as _registered_dynamic_page  # noqa: F401
    from tools.web import fetch_web_page as _registered_fetch_web_page  # noqa: F401
    from tools.web import fetch_with_cookie as _registered_cookie_page  # noqa: F401
    from tools.web import registry as web_registry

    if tool_name in {"parse_txt_document", "parse_md_document", "parse_text", "parse_markdown", "parse_docx", "parse_excel", "parse_pdf"}:
        if tool_name == "parse_text":
            tool_name = "parse_txt_document"
        elif tool_name == "parse_markdown":
            tool_name = "parse_md_document"
        return doc_registry.call_tool(tool_name, **args), "tools.document.registry.call_tool"
    if tool_name == "ocr_document":
        return ocr_registry.call_tool(tool_name, **args), "tools.ocr.registry.call_tool"
    if tool_name in {"fetch_web_page", "fetch_dynamic_page", "fetch_with_cookie"}:
        return web_registry.call_tool(tool_name, **args), "tools.web.registry.call_tool"
    if tool_name == "web_search":
        return search_registry.call_tool(tool_name, **args), "tools.search.registry.call_tool"
    if tool_name in {"extract_local_video_subtitle", "extract_web_video_subtitle"}:
        return video_registry.call_tool(tool_name, **args), "tools.video.registry.call_tool"
    if tool_name == "asr_transcribe":
        return asr_registry.call_tool(tool_name, **args), "tools.asr.registry.call_tool"
    if tool_name.startswith("prepare_"):
        return _call_v17_prepare_tool(tool_name, args, pending_svc), "services.capabilities.knowledge.pending_ingestion_service"
    if tool_name == "commit_pending":
        return _call_v17_commit_tool(args, pending_svc), "services.capabilities.knowledge.pending_ingestion_service.commit_pending"
    if tool_name == "retrieve_knowledge":
        return _call_v17_retrieve_tool(args, retrieve_knowledge), "services.capabilities.knowledge.retrieve_service.retrieve_knowledge"
    return (
        _V17ServiceToolResult(
            tool_name=tool_name,
            status="failed",
            error_code="tool_not_found",
            failure_reason=f"未支持的 V17 tool: {tool_name}",
        ),
        "v17.dispatcher",
    )


def _execute_v17_steps(
    *,
    steps: list[dict[str, Any]],
    source_tasks: list[dict[str, Any]],
    allowed: set[str],
    disabled: set[str],
    round_label: str,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[str],
]:
    analyst = SourceAnalystRuntime()
    tool_steps_summary: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    tool_calls: list[dict[str, Any]] = []
    temp_materials: list[str] = []
    source_briefs: list[dict[str, Any]] = []

    from config.cost_rule import COST

    _web_fetch_count = 0

    for idx, step in enumerate(steps):
        if idx >= COST.tool_max_steps:
            failures.append({"tool": "LIMIT", "reason": f"tool_max_steps({COST.tool_max_steps}) reached", "recoverable": False, "round": round_label, "step_id": ""})
            break
        t0 = time.monotonic()
        task = source_tasks[idx] if idx < len(source_tasks) else dict(step.get("seed_task") or {})
        if idx >= len(source_tasks):
            source_tasks.append(task)
        task["status"] = "running"
        tool_name = str(step.get("tool_name") or "")
        err = ""
        result = None
        entry = ""
        if tool_name in {"fetch_web_page", "fetch_dynamic_page", "fetch_with_cookie"}:
            _web_fetch_count += 1
            if _web_fetch_count > COST.web_fetch_max_pages:
                err = "web_fetch_max_pages_reached"
        if not err and (tool_name in disabled or (allowed and tool_name not in allowed)):
            err = "tool_disabled" if tool_name in disabled else "tool_not_allowed"
        if not err:
            args = dict(step.get("args") or {})
            result, entry = _dispatch_v17_tool(tool_name, args)
            tool_calls.append({
                "tool": tool_name,
                "params": args,
                "entry": entry,
                "result": result.to_trace_dict() if hasattr(result, "to_trace_dict") else {
                    "tool_name": tool_name,
                    "status": getattr(result, "status", "failed"),
                    "error_code": getattr(result, "error_code", ""),
                    "failure_reason": getattr(result, "failure_reason", ""),
                    "pending_id": getattr(result, "pending_id", ""),
                    "source_id": getattr(result, "source_id", ""),
                    "retrieved_chunk_ids": getattr(result, "retrieved_chunk_ids", []),
                    "text_length": len(getattr(result, "text", "") or ""),
                    "metadata": getattr(result, "metadata", {}),
                    "trace": [],
                },
                "ok": result.status == "success",
                "round": round_label,
            })
        duration_ms = int((time.monotonic() - t0) * 1000)
        from core.cost_recorder import record_tool_call as _rec_tool
        _rec_tool(tool_name, duration_ms, success=(not err and result is not None and result.status == "success"))
        if err:
            task.update({"status": "failed", "tool_result_status": "failed", "error_code": err, "failure_reason": err})
            failures.append({"tool": tool_name, "reason": err, "recoverable": True, "round": round_label, "step_id": step.get("step_id", "")})
        elif result is None or result.status != "success":
            code = getattr(result, "error_code", "") or "tool_failed"
            reason = getattr(result, "failure_reason", "") or code
            task.update({"status": "failed", "tool_result_status": getattr(result, "status", "failed"), "error_code": code, "failure_reason": reason})
            failures.append({"tool": tool_name, "reason": reason, "error_code": code, "recoverable": True, "round": round_label, "step_id": step.get("step_id", "")})
        else:
            source_id = f"web:{(result.metadata or {}).get('content_hash') or idx + 1}"
            chunk_id = f"{source_id}:chunk:1"
            task.update(
                {
                    "status": "succeeded",
                    "tool_result_status": result.status,
                    "pending_id": getattr(result, "pending_id", ""),
                    "source_id": getattr(result, "source_id", "") or source_id,
                    "retrieved_chunk_ids": getattr(result, "retrieved_chunk_ids", None) or [chunk_id],
                    "metadata": dict(result.metadata or {}, title=getattr(result, "title", ""), url=getattr(result, "url", "")),
                }
            )
            if (getattr(result, "text", "") or "").strip():
                chunks = [{"chunk_id": chunk_id, "source_id": task["source_id"], "text": result.text, "score": 1.0}]
                brief = analyst.analyze(task, chunks)
                task["source_brief_id"] = brief["source_brief_id"]
                brief["round"] = round_label
                source_briefs.append(brief)
                temp_materials.append(
                    f"SourceBrief {brief['source_brief_id']}\n标题：{brief['title']}\n角度：{brief['angle']}\n要点："
                    + "；".join(brief["key_points"][:3])
                )
        tool_steps_summary.append(
            {
                "step_id": step.get("step_id", ""),
                "tool_name": tool_name,
                "status": task.get("status", "failed"),
                "source_task_id": task.get("source_task_id", ""),
                "tool_result_status": task.get("tool_result_status", ""),
                "pending_id": task.get("pending_id", ""),
                "source_id": task.get("source_id", ""),
                "error_code": task.get("error_code", ""),
                "duration_ms": duration_ms,
                "round": round_label,
                "middle_read_step": True,
                "middle_call_entry": entry,
            }
        )
    return source_tasks, source_briefs, tool_steps_summary, failures, tool_calls, temp_materials


__all__ = ["_V17ServiceToolResult", "_dispatch_v17_tool", "_execute_v17_steps"]
