"""规则基线 `_rule_baseline`：分流 Direct / KB / External。"""

from __future__ import annotations

from schemas import MainDecision, TaskInput

from .rule_router_patterns import (
    _answer_style_hint,
    _asks_knowledge_inventory,
    _casual_social_query,
    _extended_smalltalk,
    _guess_answer_style,
    _guess_compound,
    _guess_primary_goal,
    _has_sample_file_path,
    _is_trivial_greeting,
    _looks_like_general_world_knowledge,
    _mentions_doc_project_scope,
    _mentions_project_or_repo,
    _wants_local_read_tool,
    _wants_realtime_web_task,
)


def _rule_baseline(task: TaskInput) -> MainDecision:
    """规则基线：分流 Direct / KB / External，避免通识与寒暄默认进 RAG。"""
    q = task.clean_query
    trivial = _is_trivial_greeting(q)
    doc_scope = _mentions_doc_project_scope(q)

    need_context = task.is_followup or bool((task.context_snippet or "").strip())
    need_external = bool(task.has_link)
    need_tool_local = False
    need_rag = True
    instruction = ""
    priority = "balanced"
    answer_channel = "kb"
    primary = _guess_primary_goal(task.user_query)
    compound = _guess_compound(q)
    style = _guess_answer_style(q)
    style_hint = _answer_style_hint(style, compound)

    if trivial and not task.has_link:
        need_rag = False
        need_external = False
        answer_channel = "direct"
        instruction = "用户为寒暄或极短输入：回答侧用自然、简短语气即可，不要提检索或知识库状态。"
        style = "general"
        style_hint = _answer_style_hint(style, compound)
    elif trivial and task.has_link:
        need_rag = False
        need_external = True
        answer_channel = "external"
        instruction = "寒暄但同时提供链接：不必检索知识库，优先用工具抓取链接正文要点。"
        priority = "http_first"
    elif task.has_link and not doc_scope:
        need_rag = False
        need_external = True
        need_tool_local = _wants_local_read_tool(q)
        answer_channel = "external"
        priority = "http_first"
        instruction = (
            "用户提供了 URL：优先用工具抓取页面；"
            "未明确要求查本仓库文档时不要先走知识库检索。"
        )
        if need_tool_local:
            instruction += " 若同时指定本地示例路径，可用只读工具读取 knowledge_samples 下文件。"
    elif doc_scope:
        need_rag = True
        need_tool_local = _wants_local_read_tool(q)
        answer_channel = "kb"
        instruction = (
            "用户关注文档、README、项目或系统说明：优先检索知识库中的项目/文档片段；"
            "若含 URL，再用工具抓取页面要点。"
        )
        priority = "rag_first" if not need_tool_local else "local_first"
        if task.has_link:
            need_external = True
            instruction += " 已检测到链接，请尝试用工具获取外部正文摘要。"
        if need_tool_local:
            instruction += " 若用户给出本地路径，使用只读工具读取 knowledge_samples 下 txt/md。"
    elif _asks_knowledge_inventory(q) and not task.has_link:
        need_rag = True
        need_tool_local = _wants_local_read_tool(q)
        answer_channel = "kb"
        instruction = (
            "用户在了解知识库里有哪些资料：检索已入库片段，归纳可见主题、文件名或段落线索，"
            "语气像助手介绍资料，不要只说「请自行打开文件」。"
        )
        priority = "rag_first"
        style = "general"
        style_hint = _answer_style_hint(style, compound)
    elif _wants_realtime_web_task(q) and not task.has_link:
        need_rag = False
        need_external = True
        answer_channel = "external"
        priority = "http_first"
        instruction = (
            "用户要查实时/公开信息（如天气、新闻）：必须走网页检索工具整理摘要；"
            "禁止用仓库 README 或知识库片段冒充实时结果；若检索无结果要如实说明。"
        )
        style = "general"
        style_hint = _answer_style_hint(style, compound)
    elif _extended_smalltalk(q) and not task.has_link:
        need_rag = False
        need_external = False
        answer_channel = "direct"
        instruction = "日常对话或能力询问：自然回答，不要展示内部路由/缺口标签/检索状态。"
        style = "general"
        style_hint = _answer_style_hint(style, compound)
    elif _casual_social_query(q) and not task.has_link:
        need_rag = False
        need_external = False
        answer_channel = "direct"
        instruction = "情绪/近况类闲聊：像真人助手简短回应，不要套知识库免责声明或通识长模板。"
        style = "general"
        style_hint = _answer_style_hint(style, compound)
    elif _looks_like_general_world_knowledge(q) and not task.has_link:
        need_rag = False
        need_external = False
        answer_channel = "direct"
        instruction = (
            "通识或生活常识类：直接给出通常说法，明确这不是项目知识库检索结果，"
            "勿用 not_found 等内部状态措辞。"
        )
        if style == "general":
            style = "explain"
        style_hint = _answer_style_hint(style, compound)
    else:
        need_tool_local = _wants_local_read_tool(q) or _has_sample_file_path(q)
        if _has_sample_file_path(q):
            need_rag = True
            answer_channel = "kb"
            instruction = (
                "用户给出了 knowledge_samples 下的示例路径："
                "优先用只读工具读取该文件，并可配合知识库片段。"
            )
            priority = "local_first"
        elif _mentions_project_or_repo(q):
            need_rag = True
            answer_channel = "kb"
            instruction = "问题涉及本项目/仓库/文档：检索知识库相关片段。"
            priority = "local_first" if need_tool_local else "balanced"
        elif len(q.strip()) < 24:
            need_rag = False
            answer_channel = "direct"
            instruction = "问句较短且未明确要求查资料：按日常理解直接回应，勿强行检索。"
            style = "general"
            style_hint = _answer_style_hint(style, compound)
        else:
            need_rag = True
            answer_channel = "kb"
            instruction = "检索知识库中与问题相关的片段。"
            priority = "local_first" if need_tool_local else "balanced"
        if task.has_link:
            need_external = True
            instruction += " 同时尝试通过工具抓取用户提供的链接内容。"
        if need_tool_local:
            instruction += " 需要时用只读工具读取用户指定的示例文件或列出示例目录。"

    if need_context and (task.context_snippet or "").strip():
        instruction = f"（有会话摘要）结合上文指代。{instruction}"

    return MainDecision(
        task_id=task.task_id,
        need_rag=need_rag,
        need_context=need_context,
        need_external_info=need_external,
        need_tool_local=need_tool_local,
        middle_agent_instruction=instruction.strip(),
        task_status="routed",
        primary_goal=primary,
        is_compound=compound,
        middle_collect_priority=priority,
        answer_style=style,
        answer_style_hint=style_hint,
        router_source="rules",
        llm_error="",
        answer_channel=answer_channel,
    )
