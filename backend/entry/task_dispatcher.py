"""
输入层：轻量清洗、链接检测、追问规则、封装 TaskInput。
不做复杂语义判断。
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

# 简单 URL 检测（骨架）
_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)


def _extract_has_link(text: str) -> bool:
    return bool(_URL_RE.search(text))


def _extract_link_urls(text: str) -> list[str]:
    found = _URL_RE.findall(text)
    # 去掉常见尾部标点
    cleaned: list[str] = []
    for u in found:
        u = u.rstrip(").,;，。；）】」")
        if u:
            cleaned.append(u)
    return cleaned


def _clean_query(user_query: str) -> str:
    # TODO: 按需扩展清洗规则（全角空格、多余空白等）
    return " ".join(user_query.strip().split())


def _is_followup_rule(
    session_id: str | None,
    clean_query: str,
) -> bool:
    """
    轻规则追问判断：有会话且问句较短时标为可能追问。
    TODO: 与真实产品规则对齐。
    """
    if not session_id:
        return False
    return len(clean_query) < 80


def dispatch_task(
    user_query: str,
    *,
    session_id: str | None = None,
) -> TaskInput:
    """
    将用户原始输入包装为 TaskInput。
    """
    try:
        clean = _clean_query(user_query)
        urls = _extract_link_urls(user_query)
        now = datetime.now(UTC)
        task = TaskInput(
            task_id=str(uuid.uuid4()),
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
