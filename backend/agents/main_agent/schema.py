"""
main_agent 判断对象 schema。

- `MainXiezuoPan`：主协作判维度，由 main 自己产出，下游必须尊重。
- `AgnoCollaborationPlan`：MainAgent.pan 的对外结构化返回值。

`AgnoCollaborationPlan` 的 prepare/commit 意图字段：
- v13_prepare_intent / v13_commit_intent：传递「当前轮用户是否带资料要 prepare」和
  「是否要求保存到知识库」的判断；Main 不直接执行 prepare/commit，只输出 plan，
  由 Middle 按 plan 执行工具。

真约束字段（不是 trace 装饰，Middle/Answer 必须据此决定执行路径）：
- needs_retrieval    : Middle 是否必须调 retrieve_knowledge（从 decision.need_rag 派生）
- retrieval_strategy : 传给 retrieve_knowledge 的 strategy 参数（"auto"/"keyword"/"semantic"/"hybrid"）
- needs_pending      : Middle 是否需要处理 pending/commit（从 v13_prepare_intent/v13_commit_intent 派生）
- pending_reference  : pending 操作类型 "latest"/"all"/"prepare"/"commit"/"none"
- answer_mode        : Answer 回答模式 "knowledge_grounded"/"temporary_material"/"commit_result"/"direct"/"conservative"
- tools_allowed      : Middle 本轮允许调用的工具白名单（list[str]）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from schemas import MainDecision


@dataclass(frozen=True)
class MainXiezuoPan:
    """
    main 协作判结果（维度驱动：由 MainDecision + 门控布尔推导，不按用户句式写死场景）。
    """

    renwu_lei: str  # zhijie / zhishu / waibu / hunhe：由 answer_channel 映射
    zhengju_need: bool  # 本轮是否「需要事实型依据」语境
    allow_kb: bool  # 是否允许走样例知识拉取
    allow_web: bool  # 是否允许网页补充（含显式、外部意图、或 on_kb_miss 门控）
    fengxian_yinzi: float  # 0~1，越高 → answer 侧越偏谨慎
    celue_tag: str  # 短记：与 answer_composition 对齐的拼音标签


@dataclass(frozen=True)
class V13PrepareIntent:
    """本轮「资料 prepare」意图描述（Main 判断、Middle 执行）。

    source_type : "text" / "text_file" / "web_url"（本轮支持的三类）
    raw_source  : URL / 文件名 / "" （供 Middle 调用对应 prepare 工具时使用）
    has_content : 用户是否同时提供了内容（text 直接粘贴）
    """

    source_type: str
    raw_source: str = ""
    has_content: bool = False


@dataclass(frozen=True)
class ExecutionAgentSpec:
    """Main 输出的单 worker 执行预算。"""

    name: str
    timeout_ms: int
    required: bool = False


@dataclass(frozen=True)
class ExecutionPlan:
    """Main 输出的执行计划骨架，供后续阶段扩展并发调度。"""

    deadline_ms: int
    answer_policy: str = "answer_or_partial_within_deadline"
    agents: tuple[ExecutionAgentSpec, ...] = field(default_factory=tuple)
    fallback: str = "background_task_if_timeout"


@dataclass(frozen=True)
class AgnoCollaborationPlan:
    """
    main 输出的 **协作决策**（不仅是路由标签），供 middle / answer 改变行为。

    - `force_skip_evidence`：为 True 时 middle **不得**做知识拉取（除非显式网页意图），answer 走短答策略。
    - `web_supplement_mode`：`explicit_only` = 仅显式/路由网页；`on_kb_miss_or_hint` = 允许「知识空再补搜」等既有门控。
    - `answer_composition`：answer 侧组织回答的主策略（与 `answer_style` 解耦一层，专用于 Agno 链）。
    - `xiezuo_pan`：通用协作判维度（真实驱动 middle/answer，与上列布尔/枚举一致推导）。
    - `video_url`：Main 从消息里已抽取的白名单视频 URL；Middle **优先**
      用此值驱动 `fetch_video_text`，避免再对 message 做一次 `extract_video_url`。

    prepare/commit 意图字段：
    - `v13_prepare_intent`：当 Main 判断用户本轮提供了资料（URL / 文件 / 文本）时，
      填充此字段告知 Middle 应执行哪类 prepare 工具；None 表示本轮无需 prepare。
    - `v13_commit_intent`：True = Main 判断用户想保存到知识库（跨轮场景：上轮有 pending,
      本轮说「保存」）；Middle 将据此调 commit_pending 工具。

    真约束字段（不是 trace 装饰字段，会直接影响 Middle/Answer 执行路径）：
    - `needs_retrieval`    : 是否需要知识库检索，Middle 根据此字段决定是否调 retrieve_knowledge
    - `retrieval_strategy` : retrieve_knowledge 策略（"auto"/"keyword"/"semantic"/"hybrid"）
    - `needs_pending`      : 是否需要 pending/commit 操作
    - `pending_reference`  : pending 操作引用类型（"latest"/"all"/"prepare"/"commit"/"none"）
    - `answer_mode`        : Answer 回答模式约束
      - "knowledge_grounded" : 基于 retrieved_chunks 回答
      - "temporary_material" : 基于 temporary_materials（pending 临时材料）回答
      - "commit_result"      : 基于 commit_results 说明保存结果
      - "direct"             : 直接回答，不需要材料
      - "conservative"       : 材料不足，保守说明
    - `tools_allowed`      : 本轮允许的工具白名单（空列表=不限制）
      可选值："retrieve_knowledge","prepare_text","prepare_file","prepare_web_url",
              "prepare_video","commit_pending","fetch_web","mcp_video_to_text"
    """

    decision: MainDecision
    force_skip_evidence: bool
    web_supplement_mode: str
    answer_composition: str
    xiezuo_pan: MainXiezuoPan
    video_url: str | None = field(default=None)

    # prepare/commit 意图
    v13_prepare_intent: V13PrepareIntent | None = field(default=None)
    v13_commit_intent: bool = field(default=False)

    # 真约束字段（有默认值，向后兼容；下游必须消费，不得仅写 trace）
    needs_retrieval: bool = field(default=False)
    retrieval_strategy: str = field(default="auto")   # auto/keyword/semantic/hybrid/source_all
    needs_pending: bool = field(default=False)
    pending_reference: str = field(default="none")    # latest/all/prepare/commit/none
    answer_mode: str = field(default="direct")        # knowledge_grounded/temporary_material/commit_result/direct/conservative
    tools_allowed: tuple[str, ...] = field(default_factory=tuple)  # 空元组=明确禁止所有工具；None=不限制（旧plan兼容）；("*",)=显式允许所有
    # 检索过滤条件，由 Middle 传入 retrieve_knowledge(filters=...)
    # 当前由 Middle 在会话锚点处自动生成 {"source_id": anchor.source_id}
    # 普通检索时为 None（不过滤）；plan 层也可由 Main 直接填充
    retrieval_filters: dict[str, str] | None = field(default=None)
    # 多来源任务建模。Main 只产出可执行计划，Middle 执行。
    job_type: str = field(default="normal_chat")
    source_inputs: tuple[str, ...] = field(default_factory=tuple)
    tool_plan: dict[str, Any] | None = field(default=None)
    analysis_job: dict[str, Any] | None = field(default=None)
    fallback_steps: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    tools_disabled: tuple[str, ...] = field(default_factory=tuple)
    privacy_scope: str = field(default="")
    budget_policy: dict[str, Any] | None = field(default=None)
    max_rounds: int = field(default=0)
    original_user_intent: str = field(default="")
    execution_plan: ExecutionPlan | None = field(default=None)
    # SLA / budget 元信息（由 chat 主链入口回填；不改变 Main 自身签字逻辑）
    sla_budget_ms: int = field(default=0)
    deadline_monotonic: float = field(default=0.0)
    remaining_ms_hint: int = field(default=0)
    main_elapsed_ms: int = field(default=0)
    middle_elapsed_ms: int = field(default=0)
    answer_started_remaining_ms: int = field(default=0)
