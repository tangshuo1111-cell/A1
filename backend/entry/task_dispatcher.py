"""
TaskInput 包装与 task_id 发放。

主链 complex / MainAgent 仅使用 ``issue_task_id()`` 作关联 ID，不做路由判断。
``dispatch_task`` 为 compat / rule_router 保留完整 TaskInput（含链接提取）；
``is_followup`` 仅 compat 只读提示，追问语义以 ingress 与 session history 为准。
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import UTC, datetime

from debug_trace import trace
from observability import log_phase
from schemas import TaskInput

logger = logging.getLogger("light_maqa")

# 简单 URL 检测
_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)


def issue_task_id() -> str:
    """为主链一次 agent/tool 调用分配关联 ID（非路由、非判断）。"""
    return str(uuid.uuid4())


def _extract_has_link(text: str) -> bool:
    return bool(_URL_RE.search(text))


def _extract_link_urls(text: str) -> list[str]:
    found = _URL_RE.findall(text)
    cleaned: list[str] = []
    for u in found:
        u = u.rstrip(").,;，。；）】」")
        if u:
            cleaned.append(u)
    return cleaned


def _clean_query(user_query: str) -> str:
    return " ".join(user_query.strip().split())


def _is_followup_rule(
    session_id: str | None,
    clean_query: str,
) -> bool:
    """compat 只读启发式；主链追问由 SessionHistorySnapshot / ingress 承担。"""
    if not session_id:
        return False
    return len(clean_query) < 80


def dispatch_task(
    user_query: str,
    *,
    session_id: str | None = None,
) -> TaskInput:
    """将用户原始输入包装为 TaskInput（compat / rule_router 入口）。"""
    try:
        clean = _clean_query(user_query)
        urls = _extract_link_urls(user_query)
        now = datetime.now(UTC)
        task = TaskInput(
            task_id=issue_task_id(),
            user_query=user_query,
            clean_query=clean,
            has_link=_extract_has_link(user_query),
            link_urls=urls,
            is_followup=_is_followup_rule(session_id, clean),
            session_id=session_id,
            created_at=now,
        )
    except Exception:
        logger.exception("dispatch_task: 构建 TaskInput 失败")
        raise

    trace(
        f"task_dispatcher.dispatch_task task_id={task.task_id} "
        f"has_link={task.has_link} is_followup={task.is_followup} links={len(task.link_urls)}"
    )
    log_phase(
        task.task_id,
        "dispatch_done",
        f"session_id={session_id!r} followup={task.is_followup}",
    )
    return task
