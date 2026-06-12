"""Main fallback 规则集。

包含两组：
1. V10 主路由 fallback（第 3 道意图兜底，上限 6 条）
2. V13 prepare/commit fallback（高置信硬规则，上限 5 条）

边界不变量见 ``rule_router.py`` 与本文头部说明。
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# V10 fallback（与 rule_router 口径对齐）
# ---------------------------------------------------------------------------

MAX_FALLBACK_RULES: int = 6

_SIMPLE_HI = frozenset({"你好", "您好", "hello", "hi", "在吗", "在么"})

_SAMPLE_PATH_RE = re.compile(
    r"(data[/\\]samples?[/\\]|data/README|\.env\.example|sample_success\.\w+)",
    re.IGNORECASE,
)


def _has_sample_file_path(clean_query: str) -> bool:
    return bool(_SAMPLE_PATH_RE.search(clean_query))


_KB_INVENTORY_PHRASES = (
    "知识库里有什么", "知识库有什么", "库里有什么", "有什么材料", "已入库",
    "知识库包含", "知识库列表", "list knowledge", "知识库内容",
    "有哪些文档", "有什么文档", "示例有哪些", "样例有哪些",
)

_PROJECT_ANCHOR_WORDS = frozenset({
    "本项目", "本仓库", "本系统", "仓库里", "项目里", "该系统", "该项目", "该仓库",
    "这个项目", "这个系统", "这个仓库",
})
_PROJECT_KB_QUERY_WORDS = frozenset({
    "支持", "能力", "功能", "有哪些", "是什么", "做什么", "包含哪些",
    "怎么用", "如何", "主题", "资料", "知识", "架构", "设计", "实现",
    "协作", "路由", "Agent", "agent", "材料", "检索", "索引", "向量",
    "embedding", "chunk", "入库", "语料", "resource", "document",
})


def _asks_knowledge_inventory(clean: str) -> bool:
    q = clean.strip()
    lower = q.lower()
    if "知识库" in q and any(
        x in q for x in ("什么", "哪些", "有啥", "列出", "包含", "收录", "多少")
    ):
        return True
    for p in _KB_INVENTORY_PHRASES:  # noqa: SIM110
        if p in lower:
            return True
    return False


_REALTIME_WEB_MARKERS = (
    "今天", "最新", "实时", "当前", "现在",
    "刚刚", "just now", "latest", "recent",
)
_REALTIME_WEB_ACTION = (
    "搜索", "搜一下", "查一下", "帮我查", "查询一下", "查一查", "帮我搜",
    "去网站", "网上查", "网站查询", "官网", "打开网站", "search", "look up", "find",
)
_WEATHER_WORDS = ("天气", "气温", "气象", "下雨", "降雨", "下雪", "预报", "weather", "forecast")


def _wants_realtime_web_task(clean: str) -> bool:
    q = clean.strip()
    if not q or _asks_knowledge_inventory(q):
        return False
    lower = q.lower()
    has_weather = any(k in q for k in _WEATHER_WORDS if not k.isascii()) or any(
        k in lower for k in ("weather", "forecast")
    )
    if has_weather:
        return True
    has_time = any(m in lower for m in _REALTIME_WEB_MARKERS)
    has_action = any(a in lower for a in _REALTIME_WEB_ACTION)
    if has_time and has_action:
        return True
    return "去" in q and "网" in q and any(x in q for x in ("查", "看", "搜", "找"))


def _asks_project_kb_question(clean: str) -> bool:
    has_anchor = any(w in clean for w in _PROJECT_ANCHOR_WORDS)
    has_kb_word = any(w in clean for w in _PROJECT_KB_QUERY_WORDS)
    return has_anchor and has_kb_word


# 四种主意图
_VALID_INTENTS: frozenset[str] = frozenset(
    {"zhijie_yitu", "zhishu_yitu", "waibu_yitu", "hunhe_yitu"}
)


def _v10_fallback_intent_from_high_confidence_rules(message: str) -> tuple[str, str]:
    """极少量高置信兜底（fallback 第 3 道）。

    返回 (intent, hit_rule_short_name)。default 一律保守 zhijie_yitu。
    """
    assert MAX_FALLBACK_RULES >= 4, "fallback 规则上限被误改"

    msg = (message or "").strip()
    if not msg:
        return "zhijie_yitu", "empty_default"
    if _asks_knowledge_inventory(msg):
        return "zhishu_yitu", "asks_kb_inventory"
    if _wants_realtime_web_task(msg):
        return "waibu_yitu", "realtime_web_task"
    if _has_sample_file_path(msg):
        return "zhishu_yitu", "sample_file_path"
    if _asks_project_kb_question(msg):
        return "zhishu_yitu", "project_kb_question"
    return "zhijie_yitu", "default_conservative"


# ---------------------------------------------------------------------------
# V13 prepare/commit fallback
# ---------------------------------------------------------------------------

_V13_COMMIT_HARD_PHRASES: tuple[str, ...] = (
    "保存到知识库", "存入知识库", "入库", "存到知识库", "保存到库",
    "把这个存", "把它存", "以后也要用", "存起来", "保存这个",
    "确认保存", "这个可以入库", "save to knowledge",
)

_URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)

_V13_FILE_PREPARE_TRIGGERS: tuple[str, ...] = (
    "上传了一个", "上传了个", "我传了个", "我传了一个",
    "先看看文件", "先解析文件", "先别保存", "先看文件",
    "拖了个文件", "拖入了文件",
    "解析这份文档", "解析这个文档", "解析这份文件", "解析文档",
    "这份文档", "这份 pdf", "这份pdf", "这个 pdf", "这个pdf",
    "扫描版", "扫描件", "ocr",
)

_V13_FILE_EXT_RE = re.compile(r"\b\w+\.(txt|md|pdf|docx|xlsx|xlsm)\b", re.IGNORECASE)


def v13_fallback_commit_intent(message: str) -> bool:
    """V13 高置信 commit 兜底：消息明确表达保存到知识库意图。"""
    msg = (message or "").strip()
    if not msg:
        return False
    lower = msg.lower()
    for phrase in _V13_COMMIT_HARD_PHRASES:  # noqa: SIM110
        if phrase.lower() in lower:
            return True
    return False


def v13_fallback_prepare_web_url(message: str) -> tuple[bool, str]:
    """V13 高置信 prepare_web_url 兜底：消息中含 http(s) URL + 抓取意图。"""
    msg = (message or "").strip()
    if not msg:
        return False, ""
    m = _URL_RE.search(msg)
    if m:
        url = m.group(0)
        _fetch_hints = ("抓", "看看", "先看", "预览", "先读", "读取", "获取", "fetch", "read")
        lower = msg.lower()
        if any(h in lower for h in _fetch_hints):
            return True, url
        return False, url
    return False, ""


def v13_fallback_prepare_file(message: str) -> tuple[bool, str]:
    """V13 高置信 prepare_file 兜底：消息明确提到了文件 + 先看/先解析。"""
    msg = (message or "").strip()
    if not msg:
        return False, ""
    for trigger in _V13_FILE_PREPARE_TRIGGERS:
        if trigger in msg:
            m = _V13_FILE_EXT_RE.search(msg)
            return True, m.group(0) if m else ""
    return False, ""


# 视频来源高置信 fallback
_V13_LOCAL_VIDEO_EXT_RE = re.compile(r"\b\w+\.mp4\b", re.IGNORECASE)
_V13_PATH_STOP_CHARS = frozenset(
    " \t\r\n\u3000" "\"'`" "<>|" ",;!?"
    "\uff0c\uff1b\u3002\u3001\uff01\uff1f" "\uff1a"
)
_V13_VIDEO_FILE_TRIGGERS: tuple[str, ...] = (
    "上传了一个视频", "上传了个视频", "我传了个视频",
    "先看看这个视频", "先看这个视频", "先看看这个mp4",
    "先看看视频", "这个视频帮我看", "先提取视频", "先解析视频", "先看看mp4",
)

_VIDEO_SITE_DOMAINS_RE = re.compile(
    r"https?://(www\.)?(bilibili\.com|youtube\.com|youtu\.be|"
    r"v\.qq\.com|iqiyi\.com|youku\.com|douyin\.com|kuaishou\.com)[/\s]",
    re.IGNORECASE,
)

_V13_WEB_VIDEO_VIEW_HINTS: tuple[str, ...] = (
    "先看看", "先看", "先提取", "先获取", "看看视频", "视频内容", "字幕", "提取字幕",
)


def _extract_local_mp4_path(message: str) -> str:
    """从自由文本里抽取最长的本地 .mp4 路径。"""
    msg = (message or "").strip()
    if not msg:
        return ""
    low = msg.lower()
    if ".mp4" not in low:
        return ""

    candidates: list[str] = []
    pos = 0
    while True:
        idx = low.find(".mp4", pos)
        if idx < 0:
            break
        end = idx + 4
        start = idx
        while start > 0 and msg[start - 1] not in _V13_PATH_STOP_CHARS:
            start -= 1
        candidate = msg[start:end].strip()
        if candidate.lower().endswith(".mp4"):
            candidates.append(candidate)
        pos = end

    if not candidates:
        m = _V13_LOCAL_VIDEO_EXT_RE.search(msg)
        return m.group(0) if m else ""
    candidates.sort(key=len, reverse=True)
    return candidates[0]


def v13_fallback_prepare_local_video(message: str) -> tuple[bool, str]:
    """V13 高置信 prepare_local_video 兜底：消息明确提到本地视频文件。"""
    msg = (message or "").strip()
    if not msg:
        return False, ""
    for trigger in _V13_VIDEO_FILE_TRIGGERS:
        if trigger in msg:
            return True, _extract_local_mp4_path(msg)
    path = _extract_local_mp4_path(msg)
    if path:
        return True, path
    return False, ""


def v13_fallback_prepare_web_video(message: str) -> tuple[bool, str]:
    """V13 高置信 prepare_web_video 兜底：消息含视频站 URL。"""
    msg = (message or "").strip()
    if not msg:
        return False, ""
    m = _VIDEO_SITE_DOMAINS_RE.search(msg)
    if not m:
        return False, ""
    url_start = m.start()
    _url_re = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
    um = _url_re.search(msg, pos=url_start)
    url = um.group(0) if um else m.group(0)
    return True, url


__all__ = [
    "MAX_FALLBACK_RULES",
    "_VALID_INTENTS",
    "_SIMPLE_HI",
    "_has_sample_file_path",
    "_asks_knowledge_inventory",
    "_asks_project_kb_question",
    "_wants_realtime_web_task",
    "_v10_fallback_intent_from_high_confidence_rules",
    "v13_fallback_commit_intent",
    "v13_fallback_prepare_web_url",
    "v13_fallback_prepare_file",
    "v13_fallback_prepare_local_video",
    "v13_fallback_prepare_web_video",
]
