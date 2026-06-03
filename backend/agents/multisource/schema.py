"""V17 multisource job and ToolPlan helpers."""

from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime
from typing import Any

from video.url_fetch import is_supported_video_url

_URL_RE = re.compile(r"https?://[^\s<>\]\)\"'，。；、]+", re.I)


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def extract_url_sources(message: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for m in _URL_RE.findall(message or ""):
        url = m.rstrip(".,;:!?)]}")
        if url not in seen:
            seen.add(url)
            out.append(url)
    return out


def build_analysis_job(message: str, sources: list[str]) -> dict[str, Any]:
    job_id = f"v17job_{uuid.uuid4().hex[:10]}"
    created = now_iso()
    source_tasks = []
    steps = []
    fallback_steps = []
    for idx, raw in enumerate(sources):
        stid = f"{job_id}_source_{idx + 1}"
        step_id = f"fetch_source_{idx + 1}"
        is_video = is_supported_video_url(raw)
        input_type = "web_video" if is_video else "web_url"
        tool_name = "extract_web_video_subtitle" if is_video else "fetch_web_page"
        fallback_tool_name = "fetch_web_page" if is_video else "fetch_dynamic_page"
        fallback_reason = "补抓视频落地页元数据或字幕线索" if is_video else "补抓网页正文证据"
        source_tasks.append(
            {
                "source_task_id": stid,
                "job_id": job_id,
                "source_index": idx,
                "raw_input": raw,
                "input_type": input_type,
                "tool_step_id": step_id,
                "tool_name": tool_name,
                "status": "queued",
                "tool_result_status": "",
                "pending_id": "",
                "source_id": "",
                "retrieved_chunk_ids": [],
                "source_brief_id": "",
                "error_code": "",
                "failure_reason": "",
                "metadata": {},
            }
        )
        steps.append(
            {
                "step_id": step_id,
                "tool_name": tool_name,
                "input_from": f"source_inputs[{idx}]",
                "args": {"url": raw},
                "save_as": f"source_tasks[{idx}].tool_result",
                "on_success": "build_source_task",
                "on_failure": "mark_source_failed",
                "timeout_seconds": 20,
                "max_cost": 0,
                "privacy_scope": "public_web",
                "required": False,
                "result_mapping": {
                    "source_id": "metadata.content_hash",
                    "text": "text",
                    "title": "title",
                    "url": "url",
                    "chunks": "retrieved_chunk_ids",
                },
            }
        )
        fallback_steps.append(
            {
                "step_id": f"fallback_{fallback_tool_name}_{idx + 1}",
                "source_task_id": stid,
                "source_index": idx,
                "tool_name": fallback_tool_name,
                "args": {"url": raw},
                "privacy_scope": "public_web",
                "max_cost": 0,
                "required": False,
                "reason": fallback_reason,
            }
        )
    allowed_tools = sorted(
        {
            step.get("tool_name", "")
            for step in steps + fallback_steps
            if step.get("tool_name")
        }
    )
    tool_plan = {
        "plan_id": f"v17plan_{uuid.uuid4().hex[:10]}",
        "job_type": "multi_source_compare",
        "source_count": len(sources),
        "steps": steps,
        "fallback_steps": fallback_steps,
        "tools_allowed": allowed_tools,
        "tools_disabled": [],
        "privacy_scope": "public_web",
        "max_rounds": 1,
        "budget_policy": {"max_cost": 0, "partial_allowed": True, "paid_ocr_authorized": False, "paid_asr_authorized": False},
    }
    return {
        "job_id": job_id,
        "job_type": "multi_source_compare",
        "user_query": message,
        "source_count": len(sources),
        "source_tasks": source_tasks,
        "tool_plan": tool_plan,
        "status": "queued",
        "created_at": created,
        "updated_at": created,
        "partial_allowed": True,
        "final_answer_mode": "source_brief_summary",
        "trace": {
            "v17_job_id": job_id,
            "v17_job_type": "multi_source_compare",
            "v17_source_count": len(sources),
        },
    }


def build_tool_audit_job(message: str) -> dict[str, Any] | None:
    marker = "V17_TOOL_AUDIT:"
    if marker not in (message or ""):
        return None
    raw = message.split(marker, 1)[1].strip()
    try:
        payload = json.loads(raw)
    except (ValueError, TypeError):
        return None
    steps_in = list(payload.get("steps") or [])
    if not steps_in:
        return None
    job_id = f"v17job_{uuid.uuid4().hex[:10]}"
    created = now_iso()
    steps: list[dict[str, Any]] = []
    source_tasks: list[dict[str, Any]] = []
    allowed: list[str] = []
    for idx, item in enumerate(steps_in):
        tool_name = str(item.get("tool_name") or "")
        step_id = str(item.get("step_id") or f"audit_step_{idx + 1}")
        raw_input = str(item.get("raw_input") or item.get("args", {}).get("url") or item.get("args", {}).get("file_path") or tool_name)
        allowed.append(tool_name)
        source_tasks.append(
            {
                "source_task_id": f"{job_id}_source_{idx + 1}",
                "job_id": job_id,
                "source_index": idx,
                "raw_input": raw_input,
                "input_type": str(item.get("input_type") or "tool_audit"),
                "tool_step_id": step_id,
                "tool_name": tool_name,
                "status": "queued",
                "tool_result_status": "",
                "pending_id": "",
                "source_id": "",
                "retrieved_chunk_ids": [],
                "source_brief_id": "",
                "error_code": "",
                "failure_reason": "",
                "metadata": {},
            }
        )
        steps.append(
            {
                "step_id": step_id,
                "tool_name": tool_name,
                "input_from": str(item.get("input_from") or f"audit_inputs[{idx}]"),
                "args": dict(item.get("args") or {}),
                "save_as": f"source_tasks[{idx}].tool_result",
                "on_success": str(item.get("on_success") or "build_source_task"),
                "on_failure": str(item.get("on_failure") or "mark_source_failed"),
                "timeout_seconds": int(item.get("timeout_seconds") or 30),
                "max_cost": item.get("max_cost", 0),
                "privacy_scope": str(item.get("privacy_scope") or "local_or_test"),
                "required": bool(item.get("required", False)),
                "result_mapping": dict(item.get("result_mapping") or {"status": "status", "text": "text"}),
            }
        )
    tool_plan = {
        "plan_id": f"v17plan_{uuid.uuid4().hex[:10]}",
        "job_type": "tool_audit",
        "source_count": len(steps),
        "steps": steps,
        "fallback_steps": [],
        "tools_allowed": sorted(set(allowed)),
        "tools_disabled": list(payload.get("tools_disabled") or []),
        "privacy_scope": "local_or_test",
        "max_rounds": 1,
        "budget_policy": {"max_cost": 0, "partial_allowed": True},
    }
    return {
        "job_id": job_id,
        "job_type": "tool_audit",
        "user_query": message,
        "source_count": len(steps),
        "source_tasks": source_tasks,
        "tool_plan": tool_plan,
        "status": "queued",
        "created_at": created,
        "updated_at": created,
        "partial_allowed": True,
        "final_answer_mode": "tool_audit_summary",
        "trace": {"v17_job_id": job_id, "v17_job_type": "tool_audit", "v17_source_count": len(steps)},
    }
