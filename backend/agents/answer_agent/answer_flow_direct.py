"""直接回复分支：`direct` 通道模板、外链不足兜底。"""

from __future__ import annotations

from debug_trace import trace
from schemas import AnswerResult, EvidencePack, MainDecision

from .prompt import _BANNED_IN_ANSWER, _DIRECT_DISCLAIMER_SHORT, _SECTION_GAP


def _strip_answer_leaks(text: str) -> str:
    """从最终用户文本中剔除内部状态/缺口标签。"""
    out = text or ""
    for w in _BANNED_IN_ANSWER:
        if w in out:
            out = out.replace(w, "")
    return out


def _map_answer_type(style: str, insufficient: bool) -> str:
    if insufficient:
        return "insufficient"
    mapping = {
        "explain": "concept_explain",
        "steps": "steps_list",
        "compare": "compare_table",
        "conclusion": "conclusion_first",
        "general": "structured_sections",
    }
    return mapping.get(style, "structured_sections")


def _asked_kb_inventory(uq: str) -> bool:
    q = uq.strip()
    return "知识库" in q and any(
        x in q for x in ("什么", "哪些", "有啥", "列出", "包含", "收录", "多少")
    )


def _assistant_persona_body(q: str) -> str | None:
    u = q.strip()
    if any(x in u for x in ("几岁", "多大", "年龄", "年纪", "哪年出生", "生日", "属什么")):
        return (
            "我是系统里的对话助手，没有真实年龄或生日这一说。"
            "平时可以正常闲聊；需要时也能按当前项目的知识库回答，或读示例文件、试公开网页摘要。"
        )
    return None


def _casual_social_body(q: str) -> str | None:
    u = q.strip()
    if any(x in u for x in ("开心", "高兴", "难过", "心情", "沮丧", "郁闷", "烦死了")):
        return (
            "谢谢惦记，我这边没有真人那种情绪波动，但运行正常。"
            "你今天怎么样？想随便聊两句，还是让我帮你查资料、读示例文件都行。"
        )
    if "你好吗" in u or "还好吗" in u or "还好么" in u:
        return "我挺好的，随时在。你想聊项目文档，还是先寒暄两句都行。"
    if any(x in u for x in ("怎么样", "好吗", "好不", "还好")) and any(
        x in u for x in ("今天", "最近", "这两天", "你现在")
    ):
        return "我还行，一直在线。你今天顺利吗？有文档或示例要看，直接说关键词或文件名就行。"
    if any(x in u for x in ("在干嘛", "在干什么", "忙什么")):
        return "在等你提问呢。想闲聊、查知识库、读示例文件，或者问点实时信息（会走网页检索时）都可以。"
    if any(x in u for x in ("吃了吗", "睡了吗", "起床了吗")):
        return "我不用吃饭睡觉哈哈。你休息得怎么样？项目上有问题也可以丢给我。"
    return None


def _is_trivial_hi(q: str) -> bool:
    c = q.strip().lower()
    if len(c) <= 8:
        return c in ("你好", "您好", "hello", "hi", "在吗", "在么", "嗨")
    return False


def _direct_body(user_query: str, decision: MainDecision) -> str:
    q = user_query.strip()
    low = q.lower()
    persona = _assistant_persona_body(q)
    if persona:
        return persona
    casual = _casual_social_body(q)
    if casual:
        return casual
    if _is_trivial_hi(q) or low in ("hello", "hi"):
        return (
            "嗨，你好！我是多 Agent 协作演示里的助手：可以正常闲聊，也能查本项目知识库、"
            "读 knowledge_samples 示例，或在开启网页检索时整理一点公开摘要。"
            "今天想先聊什么？"
        )
    if any(x in q for x in ("你能做什么", "你可以做什么", "你会什么", "能帮我什么")):
        return (
            "我能做几件事：正常闲聊和通识问答；按已导入文档做知识库回答；"
            "读你指定的示例文件；有链接时抓页面要点；需要实时信息时会尝试公开网页检索（受网络与配置影响）。"
            "你现在最想先做哪一件？"
        )
    if any(x in q for x in ("谢谢", "感谢", "辛苦了")):
        return "不客气，有需要再叫我。"
    if any(x in q for x in ("再见", "拜拜")):
        return "再见，祝顺利。"

    lowq = q.lower()
    if "易拉罐" in q or "罐头" in q:
        return (
            f"{_DIRECT_DISCLAIMER_SHORT}{_SECTION_GAP}"
            "开易拉罐饮料时，一般可以：\n"
            "1. 找到拉环，向上拉起或按下刻痕处，沿开口撕开。\n"
            "2. 开口边缘可能锋利，建议慢一些，必要时垫纸巾避免划伤。\n"
            "3. 若拉环脱落，可用汤匙柄轻轻撬开压痕处（注意安全）。"
        )
    if "python" in lowq and any(x in q for x in ("是什么", "什么是", "啥是")):
        return (
            f"{_DIRECT_DISCLAIMER_SHORT}{_SECTION_GAP}"
            "Python 是一种常用的高级编程语言，语法相对易读，广泛用于脚本、"
            "Web、数据与自动化等。要是你想问的是本仓库里怎么用 Python，跟我说下文件或场景就行。"
        )
    if "向量" in q and "数据库" in q:
        return (
            f"{_DIRECT_DISCLAIMER_SHORT}{_SECTION_GAP}"
            "向量数据库用来存和查「向量嵌入」，常见是语义搜索、推荐和 RAG。"
            "若你想对照本项目的检索配置，告诉我文档或模块名我帮你对着讲。"
        )

    if any(x in q for x in ("如何", "怎么", "怎样")):
        return (
            f"{_DIRECT_DISCLAIMER_SHORT}{_SECTION_GAP}"
            "这类问题可以想成三步：先弄清目标和限制，再列可行做法，最后留意安全和常见坑。"
            "如果你其实想问本仓库里的具体操作，补一句场景或文件名我就能往文档上靠。"
        )

    return (
        f"我主要能陪你闲聊，也能在需要时查知识库、读示例或试网页检索。"
        f"你提到的「{q[:48]}」我这边没有额外资料，我们就当聊天——"
        f"接下来想继续聊，还是问点具体问题？"
    )


def _answer_direct(
    user_query: str,
    evidence: EvidencePack,
    *,
    decision: MainDecision,
    context_snippet: str,
    channels_used: list[str] | None,
) -> AnswerResult:
    body = _direct_body(user_query, decision)
    trace(
        f"answer_agent.direct task_id={evidence.task_id} "
        f"router={decision.router_source} channel=direct"
    )
    return AnswerResult(
        task_id=evidence.task_id,
        final_answer=_strip_answer_leaks(body.strip()),
        answer_type="structured_sections",
        has_insufficient_info_notice=False,
        suggest_more_retrieval=False,
        should_save_history=True,
        task_status="succeeded",
        user_visible_status="",
        channels_used=list(channels_used or []),
        router_source=decision.router_source,
        evidence_state="",
    )


def _user_message_has_url(q: str) -> bool:
    low = q.lower()
    return "http://" in low or "https://" in low or "www." in low


def _answer_external_insufficient(
    user_query: str,
    evidence: EvidencePack,
    *,
    decision: MainDecision,
    channels_used: list[str] | None,
) -> AnswerResult | None:
    if (decision.answer_channel or "") != "external":
        return None
    has_evidence = any((e or "").strip() for e in evidence.evidence_list) or any(
        (e or "").strip() for e in evidence.key_evidence_list
    )
    if has_evidence:
        return None
    rd = evidence.retrieval_debug or {}
    web_planned = bool(rd.get("web_search_planned"))
    web_hits = int(rd.get("web_search_hit_chunks") or 0)
    uq = user_query.strip()
    has_url = _user_message_has_url(uq)

    if has_url and web_planned and web_hits == 0:
        msg = (
            "链接正文没能抓到可用片段，公开网页检索也没有返回够用的摘要。"
            "常见是页面要登录、反爬或地址有误；你也可以在浏览器里确认能打开后，把关键段落贴过来我帮你整理。"
        )
        vis = "外链与网页检索均未成功"
    elif has_url:
        msg = (
            "链接这边没能抓到可用正文，常见是页面要登录、加载慢，或者地址打错了。\n\n"
            "你可以在浏览器里先确认能打开；愿意的话把关键段落直接贴过来，我帮你整理。"
        )
        vis = "外链获取未成功"
    elif web_planned and web_hits == 0:
        msg = (
            "我按你的问题试了公开网页检索，但这次没有拿到够用的摘要。"
            "可能是网络限制、搜索源暂时不可用，或关键词太泛。"
            "可以改得更具体（例如「城市名 + 天气」），或直接打开你信任的气象网站核对。"
        )
        vis = "网页检索无有效结果"
    else:
        msg = (
            "外部资料这一步没有拿到可用内容。若你本打算让我打开某个网页，请直接贴上完整链接。"
        )
        vis = "外部渠道未成功"

    trace(f"answer_agent.external_insufficient task_id={evidence.task_id}")
    return AnswerResult(
        task_id=evidence.task_id,
        final_answer=_strip_answer_leaks(msg.strip()),
        answer_type="insufficient",
        has_insufficient_info_notice=True,
        suggest_more_retrieval=False,
        should_save_history=True,
        task_status="partial",
        user_visible_status=vis,
        channels_used=list(channels_used or []),
        router_source=decision.router_source,
        evidence_state="",
    )
