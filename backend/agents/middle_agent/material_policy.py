"""台账 G-005「material_policy」：材料侧规则算子（路径信号 / trace 标签 / KB 硬度 / tools_allowed）。

历史文件名 `runtime_helpers.py` 已废止；`_agno_*` / `_is_tool_allowed` 等别名保留，
以便 `from agents.middle_agent.runtime import _is_tool_allowed` 等既有导入不变。
"""

from __future__ import annotations

from services.capabilities.web import web_orchestration_service as agno_web_service

from .collect_flow_eval import _token_overlap

# V7 第 1 轮：从消息里抽取本地 .mp4 路径的"显式信号"算子。
# 仅做输入清洗，不替 runtime 出主结论；运行期由 `MiddleAgentRuntime.shibie_video_yitu` 调用。
#
# 算法：定位每一个 ".mp4" 出现位置，向前吃到第一个"中断符"为止。
# 中断符 = ASCII 空白 / 全角空格 / 引号 / `<>|` / 中文常见全角标点 / 行首。
# 重要：ASCII `:` **不是** 中断符——Windows 盘符 `C:\...` 必须能被完整保留；
#       中文全角 `：` 是中断符，能切掉"句子：path"前面的中文短语。
_PATH_STOP_CHARS = frozenset(
    " \t\r\n\u3000"           # 空白
    "\"'`"                    # 引号
    "<>|"                     # 不允许的路径字符
    ",;!?"                    # ASCII 半角标点（不含 `:`，盘符要用）
    "\uff0c\uff1b\u3002\u3001\uff01\uff1f"  # 中文 ， ； 。 、 ！ ？
    "\uff1a"                  # 中文冒号 ：
)


def extract_mp4_path_from_message(message: str) -> str | None:
    """规则层显式信号算子：抽取消息中的本地 .mp4 路径（最长匹配）。"""
    msg = (message or "").strip()
    if not msg:
        return None
    msg_lower = msg.lower()
    if ".mp4" not in msg_lower:
        return None

    candidates: list[str] = []
    pos = 0
    while True:
        idx = msg_lower.find(".mp4", pos)
        if idx < 0:
            break
        end = idx + 4  # 含 .mp4
        start = idx
        while start > 0 and msg[start - 1] not in _PATH_STOP_CHARS:
            start -= 1
        path = msg[start:end].strip()
        if path and path.lower().endswith(".mp4"):
            candidates.append(path)
        pos = end

    if not candidates:
        return None
    candidates.sort(key=len, reverse=True)
    return candidates[0]


def agno_route_label(message: str, *, http_use_knowledge: bool) -> str:
    """与历史 `_v4_route_label` 对齐，保证既有单测指纹不变（仅作 trace 标签）。"""
    msg = (message or "").strip()
    if http_use_knowledge:
        return "knowledge_first"
    if agno_web_service.user_requests_web_search(msg):
        return "web_explicit"
    return "direct"


def agno_kb_evidence_tier(message: str, kb: str | None) -> str:
    """规则相似度算子：判断知识摘录硬度（none / weak / strong）—— 给 runtime 当输入。"""
    body = (kb or "").strip()
    if not body:
        return "none"
    ov = _token_overlap(message, body)
    if ov < 0.045 and len(body) < 400:
        return "weak"
    if ov < 0.08 and len(body) < 200:
        return "weak"
    return "strong"


def is_tool_allowed(plan: object, tool_name: str) -> bool:
    """检查 tool_name 是否在 plan.tools_allowed 白名单中。

    最终语义（V15 R2 收边）：
    - tools_allowed 为 None 或缺失属性 → 向后兼容旧 plan，不限制（放行所有工具）
    - tools_allowed 为空元组/空列表 () → **明确禁止所有工具**（direct 模式专用）
    - tools_allowed 含 "*" 或 "__all__" → 允许所有工具（显式不限制）
    - tools_allowed 为非空元组 → 白名单模式，tool_name 必须在其中才允许

    注意：direct 普通回答本身不是工具调用，不走此函数判断。
    Answer Agent 的 direct 模式在 plan.answer_mode="direct" 时直接短路返回，
    不依赖 tools_allowed 的值，因此不会被空元组误伤。
    """
    allowed = getattr(plan, "tools_allowed", None)
    if allowed is None:
        return True  # 兼容旧 plan（未设置 tools_allowed），向后兼容放行
    allowed_set = set(allowed)
    if "*" in allowed_set or "__all__" in allowed_set:
        return True  # 显式允许所有工具
    if not allowed_set:
        return False  # 空白名单 = 明确禁止所有工具（direct 模式）
    return tool_name in allowed_set


# 与历史 monkeypatch / `from runtime import _foo` 对齐的别名
_extract_mp4_path_from_message = extract_mp4_path_from_message
_agno_route_label = agno_route_label
_agno_kb_evidence_tier = agno_kb_evidence_tier
_is_tool_allowed = is_tool_allowed

__all__ = [
    "_extract_mp4_path_from_message",
    "_agno_route_label",
    "_agno_kb_evidence_tier",
    "_is_tool_allowed",
    "extract_mp4_path_from_message",
    "agno_route_label",
    "agno_kb_evidence_tier",
    "is_tool_allowed",
]
