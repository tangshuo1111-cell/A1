"""规则路由：关键词检测、轻量猜测、答案通道护栏与相关常量。"""

from __future__ import annotations

import re

from schemas import MainDecision, TaskInput

# MAX_FALLBACK_RULES 是 fallback 边界的显式锚点（与 `rule_router.py` 头部说明一致）。
MAX_FALLBACK_RULES: int = 6  # 上限，严禁超过

# 极简问候：不触发检索/外链
_SIMPLE_HI = frozenset(
    {
        "你好",
        "您好",
        "hello",
        "hi",
        "在吗",
        "在么",
    }
)

# 与 workflow.common.extract_local_path_hints 一致：仅贴路径时也要走工具
_SAMPLE_PATH_RE = re.compile(
    r"knowledge_samples[/\\][^\s\"'<>|]+\.(?:md|txt)",
    re.IGNORECASE,
)


def _has_sample_file_path(clean_query: str) -> bool:
    return bool(_SAMPLE_PATH_RE.search(clean_query))


def _mentions_doc_project_scope(clean_query: str) -> bool:
    """是否提到文档 / README / 项目 / 链接（关键词级，非语义）。"""
    q = clean_query.strip()
    low = q.lower()
    if "readme" in low:
        return True
    for kw in ("文档", "项目", "链接"):  # noqa: SIM110
        if kw in q:
            return True
    return False


def _wants_local_read_tool(clean_query: str) -> bool:
    """是否需要本地只读工具：读文件 / 列示例目录（关键词级）。"""
    q = clean_query.strip()
    low = q.lower()
    keys = (
        "读取文件",
        "读文件",
        "打开文件",
        "read file",
        "list files",
        "知识库列表",
        "有哪些文件",
        "列出文件",
        "列出知识库",
        "knowledge_samples",
    )
    if any(k in q for k in keys):
        return True
    if "knowledge_samples" in q and "读取" in q:
        return True
    return "list files" in low


def _is_trivial_greeting(clean_query: str) -> bool:
    c = clean_query.strip()
    if len(c) <= 1:
        return True
    return c.lower() in {x.lower() for x in _SIMPLE_HI}


def _guess_compound(q: str) -> bool:
    """极轻量：问号数量、连接词。"""
    if q.count("？") + q.count("?") >= 2:
        return True
    for k in ("和", "以及", "还有", "另外", "分别", "对比", "区别"):  # noqa: SIM110
        if k in q:
            return True
    return False


def _answer_style_hint(style: str, compound: bool) -> str:
    """给回答 Agent 的自然语言提示（与 answer_style 对齐，不做路由）。"""
    hints = {
        "explain": "用概念解释型结构：先定义/直觉，再引用依据，避免堆砌术语。",
        "steps": "用步骤型结构：按顺序列要点；若证据无明确步骤，标明并退化为要点列表。",
        "compare": "用对比型结构：分维度对照；缺对立面信息时要写明缺口。",
        "conclusion": "先给收敛结论，再列依据，最后补充限制条件。",
        "general": "结论—依据—补充说明三段式；证据偏弱时降低确信度。",
    }
    base = hints.get(style, hints["general"])
    if compound:
        return base + " 本题可能为复合问，尽量分点覆盖子问题。"
    return base


def _guess_answer_style(q: str) -> str:
    low = q.lower()
    if any(k in q for k in ("步骤", "怎么做", "如何操作", "流程", "教程")):
        return "steps"
    if any(k in q for k in ("对比", "区别", "vs", "versus")) or " vs " in low:
        return "compare"
    if any(k in q for k in ("结论", "总结", "一句话")):
        return "conclusion"
    if any(k in q for k in ("是什么", "含义", "概念", "定义")):
        return "explain"
    return "general"


def _guess_primary_goal(q: str) -> str:
    s = q.strip().replace("\n", " ")
    return s[:120] if s else "（空）"


_ALLOWED_PRIORITY = frozenset({"balanced", "rag_first", "local_first", "http_first"})
_ALLOWED_STYLE = frozenset({"general", "explain", "steps", "compare", "conclusion"})

# 明显指向「本仓库 / 文档 / 系统」时才优先走知识库（避免通识问句因含泛词误进 RAG）
_PROJECT_OR_REPO_MARKERS = (
    "readme",
    "本项目",
    "本仓库",
    "本系统",
    "代码库",
    "knowledge_samples",
    "工具层",
    "workflow",
    "当前系统",
    "该仓库",
    "仓库里",
    "文档里",
    "按文档",
    "项目里",
    "项目代号",
    "项目如何",
    "项目怎么",
)


def _mentions_project_or_repo(q: str) -> bool:
    low = q.lower()
    if "readme" in low:
        return True
    return any(m in q for m in _PROJECT_OR_REPO_MARKERS if m != "readme")


def _wants_realtime_web_task(clean: str) -> bool:
    """天气、实时资讯、去网站查等：需要公开网页摘要，不能用仓库文档冒充。"""
    q = clean.strip()
    if not q or _asks_knowledge_inventory(q):
        return False
    low = q.lower()
    if _mentions_project_or_repo(q):
        weather_kw = (
            "天气",
            "气温",
            "气象",
            "下雨",
            "降雨",
            "下雪",
            "预报",
            "weather",
            "forecast",
        )
        if not any(k in q for k in weather_kw if not k.isascii()) and not any(
            k in low for k in ("weather", "forecast")
        ):
            return False
    weather_kw = (
        "天气",
        "气温",
        "气象",
        "下雨",
        "降雨",
        "下雪",
        "预报",
        "weather",
        "forecast",
    )
    if any(k in q for k in weather_kw if not k.isascii()) or any(
        k in low for k in ("weather", "forecast")
    ):
        return True
    realtime_kw = ("今天", "现在", "最新", "实时", "当前")
    web_action = (
        "帮我查",
        "查一下",
        "搜一下",
        "搜索",
        "去网站",
        "网上查",
        "查询一下",
        "查一查",
        "帮我搜",
        "网站查询",
        "官网",
        "打开网站",
    )
    if any(a in q for a in web_action) and any(t in q for t in realtime_kw):
        return True
    if "去" in q and "网" in q and any(x in q for x in ("查", "看", "搜", "找")):  # noqa: SIM103
        return True
    return False


def _asks_knowledge_inventory(clean: str) -> bool:
    """用户想了解「知识库里有什么 / 有哪些资料」——必须走 kb+RAG，勿当闲聊。"""
    q = clean.strip()
    if "知识库" in q and any(
        x in q for x in ("什么", "哪些", "有啥", "列出", "包含", "收录", "多少")
    ):
        return True
    if any(  # noqa: SIM103
        x in q
        for x in (
            "有哪些文档",
            "有什么文档",
            "示例有哪些",
            "样例有哪些",
            "库里有什么",
        )
    ):
        return True
    return False


# 针对本项目/本仓库/本系统的明显知识库问题
_PROJECT_ANCHOR_WORDS = frozenset({
    "本项目", "本仓库", "本系统", "仓库里", "项目里", "该系统", "该项目", "该仓库",
    "这个项目", "这个系统", "这个仓库",
})
_PROJECT_KB_QUERY_WORDS = frozenset({
    "支持", "能力", "功能", "有哪些", "是什么", "做什么", "包含哪些",
    "怎么用", "如何", "主题", "资料", "知识", "架构", "设计", "实现",
    "协作", "路由", "Agent", "agent",
})


def _asks_project_kb_question(clean: str) -> bool:
    """用户明确对「本项目/本仓库/本系统」提问——锚词 AND 问询词双条件命中才走 KB。"""
    q = clean.strip()
    has_anchor = any(w in q for w in _PROJECT_ANCHOR_WORDS)
    has_query = any(w in q for w in _PROJECT_KB_QUERY_WORDS)
    return has_anchor and has_query


def _casual_social_query(clean: str) -> bool:
    """情绪、近况类闲聊，不走通识百科模板。"""
    q = clean.strip()
    if not q or _mentions_project_or_repo(q) or _asks_knowledge_inventory(q):
        return False
    if any(x in q for x in ("开心", "高兴", "难过", "心情", "沮丧", "郁闷", "烦死了")):
        return True
    if "你好吗" in q or "还好吗" in q or "还好么" in q:
        return True
    if any(x in q for x in ("怎么样", "好吗", "好不", "还好")) and any(
        x in q for x in ("今天", "最近", "这两天", "你现在")
    ):
        return True
    if any(x in q for x in ("在干嘛", "在干什么", "忙什么", "吃了吗", "睡了吗", "起床了吗")):
        return True
    if any(x in q for x in ("几岁", "多大", "年龄", "年纪", "哪年出生", "生日", "属什么")):  # noqa: SIM103
        return True
    return False


def _extended_smalltalk(clean: str) -> bool:
    """扩展寒暄 / 能力询问（仍不走 RAG）。"""
    c = clean.strip()
    if not c:
        return False
    low = c.lower()
    phrases = (
        "你好吗",
        "你好啊",
        "您好",
        "谢谢",
        "感谢",
        "辛苦了",
        "再见",
        "拜拜",
        "你能做什么",
        "你可以做什么",
        "你会什么",
        "你能帮我",
        "你是谁",
        "你是什么",
        "介绍一下自己",
        "介绍一下你",
        "什么模型",
        "capabilities",
    )
    if any(p in c for p in phrases):
        return True
    return low in ("thanks", "thank you", "bye")


def _looks_like_general_world_knowledge(clean: str) -> bool:
    """通识 / 生活常识 / 基础概念（不依赖本仓库资料）。"""
    if _mentions_project_or_repo(clean):
        return False
    if len(clean) > 220:
        return False
    if any(x in clean for x in ("是什么", "什么是", "什么意思", "解释一下", "举例说明", "简单说")):
        return True
    if any(x in clean for x in ("如何", "怎么", "怎样")):
        return True
    if any(x in clean for x in ("易拉罐", "罐头", "瓶盖", "拉链")):  # noqa: SIM103
        return True
    return False


def _apply_answer_channel_guard(
    task: TaskInput,
    base: MainDecision,
    final: MainDecision,
) -> MainDecision:
    """direct：禁止 LLM 把通识问句强行改回 RAG。external：无文档/项目语境时保持工具/外链优先。"""
    if base.answer_channel == "direct":
        if task.has_link:
            return final.model_copy(
                update={
                    "need_rag": False,
                    "need_external_info": True,
                    "answer_channel": "external",
                }
            )
        return final.model_copy(
            update={
                "need_rag": False,
                "need_external_info": False,
                "need_tool_local": base.need_tool_local,
                "answer_channel": "direct",
            }
        )
    if base.answer_channel == "external" and not _mentions_doc_project_scope(task.clean_query):
        return final.model_copy(
            update={
                "need_rag": False,
                "need_external_info": True if task.has_link else final.need_external_info,
                "need_tool_local": base.need_tool_local,
                "answer_channel": "external",
            }
        )
    return final
