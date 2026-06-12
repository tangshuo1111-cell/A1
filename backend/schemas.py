"""
跨层共享的 Pydantic 数据结构（与主数据流一致：
TaskInput → MainDecision → CollectionTask → EvidencePack → AnswerResult）。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, NotRequired, TypedDict

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# G-025：统一 trace schema
# ---------------------------------------------------------------------------
class TraceContext(TypedDict, total=False):
    """贯穿 API → agent → tool → task 的统一追踪上下文。

    每次请求入口创建，沿调用链向下传递。字段均为可选（total=False），
    各层按自身职责填充。消费方（日志 / 监控 / debug 面板）统一读取此结构。
    """

    request_id: str
    session_id: str
    task_id: str
    bundle_id: str
    source_id: str
    agent_name: str
    tool_name: str
    step: str
    ts_start: str
    ts_end: str
    parent_span: str
    status: str
    error: str


class ChatTurnResult(TypedDict):
    """主链 run_agno_chat_turn 的返回契约（G-009）。

    顶层字段固定；extra 内部字段按版本演进，不在此强约束。
    所有消费方（route / 前端 / 测试）应以此 TypedDict 为契约读取字段。
    """

    ok: bool
    answer: str
    session_id: str | None
    request_id: str | None
    task_id: str | None
    answer_type: str
    task_status: str
    primary_path: str
    pipeline_ok: bool
    extra: dict[str, Any]
    workflow_elapsed_ms: NotRequired[int]
    interaction_mode_zh: NotRequired[str | None]


class TaskInput(BaseModel):
    """调度层入口任务：用户问题经轻量清洗与规则预处理后封装。"""

    task_id: str = Field(..., description="任务唯一 ID")
    user_query: str = Field(..., description="用户原始问题")
    clean_query: str = Field(..., description="清洗后的可检索/可推理文本")
    has_link: bool = Field(False, description="是否包含 URL 链接")
    link_urls: list[str] = Field(
        default_factory=list,
        description="从用户输入中提取的 HTTP(S) 链接列表",
    )
    is_followup: bool = Field(False, description="是否判为追问（仅规则，非语义）")
    session_id: str | None = Field(None, description="会话 ID，可选")
    created_at: datetime = Field(..., description="任务创建时间")
    context_snippet: str = Field(
        default="",
        description="主链注入的短期会话上下文（非用户直输）",
    )


class MainDecision(BaseModel):
    """main_agent 输出：主路由判断，不检索、不生成最终回答。"""

    task_id: str = Field(..., description="关联任务 ID")
    need_rag: bool = Field(False, description="是否需要知识库检索")
    need_context: bool = Field(False, description="是否需要补历史/会话上下文")
    need_external_info: bool = Field(False, description="是否需要外部资料/工具/MCP")
    need_tool_local: bool = Field(
        False,
        description="是否需要本地只读工具（读示例目录内 txt/md、列文件）",
    )
    middle_agent_instruction: str = Field(
        default="",
        description="给 middle_agent 的自然语言行动说明（可为空表示跳过资料阶段）",
    )
    task_status: str = Field(
        default="pending",
        description="任务状态标记，如 pending / routed / error",
    )
    # 主判断扩展（保持字段名稳定、含义直白）
    primary_goal: str = Field(default="", description="用户主目标一句话")
    is_compound: bool = Field(default=False, description="是否复合/多问合一")
    middle_collect_priority: str = Field(
        default="balanced",
        description="资料收集优先级：balanced | rag_first | local_first | http_first",
    )
    answer_style: str = Field(
        default="general",
        description="回答组织偏好：general | explain | steps | compare | conclusion",
    )
    answer_style_hint: str = Field(
        default="",
        description="给 answer_agent 的自然语言风格提示（中文短句，与 answer_style 一致）",
    )
    router_source: str = Field(
        default="rules",
        description="路由来源：rules | llm | hybrid（对外说明里 hybrid 即 mixed/混合）",
    )
    llm_error: str = Field(default="", description="LLM 路由失败时的说明（空表示无错误）")
    routing_brief: str = Field(
        default="",
        description="主判断一句话摘要（标志位+优先收集+回答侧重），供日志/ middle 摘要引用",
    )
    routing_explain: str = Field(
        default="",
        description="为何给出当前路由（中文短句）：规则/LLM/混合 的可读说明",
    )
    answer_channel: str = Field(
        default="kb",
        description=(
            "用户回答通道：direct=寒暄/通识，不经资料收集；"
            "kb=依赖知识库；external=优先外链/工具（不先 RAG）"
        ),
    )


class CollectionTask(BaseModel):
    """workflow 根据 MainDecision 生成，交给 middle_agent 执行资料收集。"""

    task_id: str = Field(..., description="关联任务 ID")
    search_query: str = Field(..., description="用于 RAG/搜索的查询串")
    collection_goal: str = Field(..., description="本轮收集资料的目标说明")
    available_channels: list[str] = Field(
        default_factory=list,
        description="可用渠道：如 rag / tool / mcp 等标识",
    )
    link_urls: list[str] = Field(
        default_factory=list,
        description="本轮关联的用户链接，供 tool 拉取（由 workflow 从 TaskInput 填入）",
    )
    enable_local_file_tools: bool = Field(
        False,
        description="是否允许 middle 调用本地只读文件类工具",
    )
    local_path_hints: list[str] = Field(
        default_factory=list,
        description="从用户问题中解析出的相对路径提示（如 knowledge_samples/sample.md）",
    )
    completion_rule: str = Field(
        default="",
        description="轻量完成规则说明（骨架占位，业务后续补）",
    )
    middle_collect_priority: str = Field(
        default="balanced",
        description="与 MainDecision 对齐，供 middle 排序执行",
    )
    is_compound: bool = Field(default=False, description="是否复合问题（影响缺口判断）")
    routing_brief: str = Field(
        default="",
        description="来自 main_agent 的 routing_brief，供资料摘要引用",
    )
    rag_search_queries: list[str] = Field(
        default_factory=list,
        description="RAG 专用：按序尝试的检索串；空则 middle 仅用 search_query",
    )
    enable_web_search: bool = Field(
        default=False,
        description="是否允许外部 Web 检索（如 DDG HTML，受配置开关控制）",
    )


class EvidencePack(BaseModel):
    """middle_agent 输出：证据与自评，供 answer_agent 生成最终回答。"""

    task_id: str = Field(..., description="关联任务 ID")
    source_list: list[str] = Field(
        default_factory=list,
        description="来源标识或简述列表",
    )
    evidence_list: list[str] = Field(
        default_factory=list,
        description="证据片段或要点列表",
    )
    key_evidence_list: list[str] = Field(
        default_factory=list,
        description="middle 判定的关键证据子集（已弱化明显噪声/重复）",
    )
    noise_notes: list[str] = Field(
        default_factory=list,
        description="哪些材料像噪声或低价值（短文本、重复、纯 MCP 握手等）",
    )
    evidence_summary: str = Field(default="", description="证据综合摘要")
    completeness_ok: bool = Field(True, description="资料完整性是否可接受")
    time_validity_ok: bool = Field(True, description="时效性是否可接受")
    time_validity_note: str = Field(
        default="",
        description="时效性说明：轻规则生成，非网页抓取日期解析",
    )
    missing_info: str = Field(default="", description="仍缺的信息说明")
    need_more_info: bool = Field(False, description="是否建议继续补资料")
    coverage_score: float = Field(
        default=0.0,
        description="0~1 粗粒度自评（字数/条数/渠道覆盖）",
    )
    gap_notes: list[str] = Field(
        default_factory=list,
        description="具体缺口要点列表",
    )
    next_channel_suggestion: str = Field(
        default="",
        description="建议下一步优先补的渠道（短文本）",
    )
    refine_attempted: bool = Field(
        default=False,
        description="是否已做过一次补检索（防止重 loop）",
    )
    collection_trace: list[str] = Field(
        default_factory=list,
        description="收集审计：优先通道、补检索、次优渠道等关键步骤",
    )
    secondary_channel_attempted: str = Field(
        default="",
        description="次优渠道单步补采标识（如 rag_second_pass），空表示未执行",
    )
    why_still_insufficient: str = Field(
        default="",
        description="若仍不满足完整性，用一句话汇总原因（便于联调/演示）",
    )
    evidence_state: str = Field(
        default="ok",
        description=(
            "资料状态粗分：not_found | channel_failed | weak_hit | "
            "stale_or_unverified | ok"
        ),
    )
    gap_categories: list[str] = Field(
        default_factory=list,
        description=(
            "缺口类型标签：如 zero_rag_hit、url_failed、local_file_failed、"
            "thin_evidence、time_uncertain"
        ),
    )
    next_best_channel: str = Field(
        default="",
        description="与 next_channel_suggestion 同义，下一优先渠道（机器可读短码）",
    )
    retrieval_debug: dict[str, object] = Field(
        default_factory=dict,
        description="开发者向：RAG 尝试串、kb 行数、miss 原因等，供 extra / 调试侧栏",
    )


class AnswerResult(BaseModel):
    """answer_agent 输出：最终用户可见结果及元信息。"""

    task_id: str = Field(..., description="关联任务 ID")
    final_answer: str = Field(..., description="最终回答正文")
    answer_type: str = Field(
        default="text",
        description=(
            "回答形式：concept_explain | procedural_steps | comparison | "
            "structured_sections | insufficient 等"
        ),
    )
    has_insufficient_info_notice: bool = Field(
        False,
        description="是否在回答中提示信息不足",
    )
    suggest_more_retrieval: bool = Field(
        False,
        description="是否建议用户触发进一步检索/补资料",
    )
    should_save_history: bool = Field(True, description="是否写入会话历史")
    task_status: str = Field(default="done", description="收口状态，如 done / failed / partial")
    user_visible_status: str = Field(
        default="",
        description="给用户看的短状态说明（可选）",
    )
    channels_used: list[str] = Field(
        default_factory=list,
        description="本轮 middle 实际用到的渠道快照（供记录与演示，与 extra 对齐）",
    )
    router_source: str = Field(
        default="",
        description="主判断路由来源快照（与 MainDecision.router_source 一致，便于日志/存储对齐）",
    )
    evidence_state: str = Field(
        default="",
        description="资料状态快照（与 EvidencePack.evidence_state 一致）",
    )


# 工作流层可选：把一轮完整产出打包（便于 app 层返回）
class ChatFlowResult(BaseModel):
    """一轮对话流水线结果（workflow 收口）。"""

    task: TaskInput
    decision: MainDecision
    collection: CollectionTask | None = None
    evidence: EvidencePack | None = None
    answer: AnswerResult
    extra: dict[str, Any] = Field(default_factory=dict, description="调试或扩展字段")
