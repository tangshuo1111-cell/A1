"""
middle_agent 判断对象 schema。

- `CailiaoPan`：材料判维度，由 middle 自己产出，answer 必须尊重。
- `AgnoMaterialBundle`：MiddleAgent.caipan 的对外结构化返回值。

`AgnoMaterialBundle` 主字段（Answer 默认取材来源，优先于 knowledge_block/web_block）：
- retrieved_chunks    : 结构化 chunk 列表（统一出口）；knowledge_block 由其拼接而成
- bundle_id           : 唯一标识本次 Middle 执行产出
- plan_id             : 对应的 Main plan 标识（来自 decision.task_id）
- execution_status    : "ok"/"partial"/"failed"
- tool_calls          : 本轮实际调用的工具记录列表（list[dict]）
- temporary_materials : pending 临时材料文本列表（list[str]）
- commit_results      : commit 结果列表（list[dict]，含 source_id/chunk_count/status）
- failures            : 本轮失败记录列表（list[dict]，含 tool/reason/recoverable）
- material_sufficiency: 材料充足性摘要（"sufficient"/"insufficient"/"no_match"/"low_confidence"）

Answer 应优先从这些主字段取材，knowledge_block/web_block 降为兼容辅助字段。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from application.chat.chat_contracts import KbSufficiencyLevel

if TYPE_CHECKING:
    pass


@dataclass(frozen=True)
class CailiaoPan:
    """middle 材料判结果（由重叠度、分块、门控等连续/枚举量推出，不绑用户例句）。"""

    gou: bool  # 材料是否够支撑一轮「像样的」直答尝试
    kb_qiangdu: float  # 问句与知识摘录 token 重叠，0~1
    bukong_xinhao: str  # ok / que / ruo：不足信号，供 answer 组织策略
    laiyuan_zhu: str  # wu / kb / web / hunhe：主支撑来源归类
    use_kb: bool  # 本轮是否真的拉过/持有 kb 块
    use_web: bool  # 本轮是否持有网页块
    que_shenme: str  # none / kb_yangben / web_yinzheng / liangzhe：缺什么
    xia_yi_bu: str  # zhi_da / wen_yonghu / bu_wang / shou_kou：建议下一步


@dataclass(frozen=True)
class EvidenceEnvelope:
    """Middle worker 的单来源标准返回；不拥有最终签字权。"""

    source_type: str
    status: str
    text: str = ""
    summary: str = ""
    confidence: float = 0.0
    elapsed_ms: int = 0
    error_code: str = ""
    next_action: str = ""
    task_id: str = ""


@dataclass(frozen=True)
class AgnoMaterialBundle:
    """`/chat/agno` 资料阶段输出（middle 为判断者，RAG/Web 仍由既有 service 执行）。

    视频 MCP 透传字段（仅"额外透传"，不影响 cailiao_pan 主判断）：
    - `mcp_video_text` / `mcp_video_source` / `mcp_video_path`：当 middle 在本轮判定
      "出现视频任务"并真实通过 MCP 调起业务型 tool `video_to_text` 时，
      把抽出的可入库纯文本 + 最小来源标识透传到下游；
    - `mcp_video_ok` / `mcp_video_error`：MCP 调用成功 / 失败的明确收口；
    - `mcp_video_decision`：middle runtime 自家 `pan_jubu_celue_video` 给出的
      调用判断标签（`call_video_to_text` / `skip_no_video_yitu` 等），便于断言
      "调用决策权在 middle agent，不在 service / api"。

    所有视频字段都是默认值"零侵入"，既有调用点不需要任何改动；
    `cailiao_pan` 主判断字段仍由 middle 的五段方法直接产出，与视频字段彼此正交。

    主字段（Answer 默认取材来源，优先于 knowledge_block/web_block）：
    - bundle_id            : 本次 Middle 执行的唯一 ID（自动生成）
    - plan_id              : 对应 Main plan 的标识（来自 decision.task_id）
    - execution_status     : "ok"/"partial"/"failed"
    - tool_calls           : 工具调用记录 list[dict]（tool/params/result/ok）
    - temporary_materials  : pending 临时材料文本 list[str]
    - commit_results       : commit 结果 list[dict]（source_id/chunks/status/title）
    - failures             : 失败记录 list[dict]（tool/reason/recoverable）
    - material_sufficiency : 材料充足性 "sufficient"/"insufficient"/"no_match"/"low_confidence"
    """

    knowledge_block: str | None
    web_block: str | None
    trace: list[str]
    knowledge_adequate: bool
    material_still_insufficient: bool
    web_judgment_reason: str
    kb_evidence_tier: str
    insufficiency_signal: str
    cailiao_pan: CailiaoPan
    kb_sufficiency_level: KbSufficiencyLevel = "none"
    kb_sufficiency_reasons: tuple[str, ...] = ()
    # 结构化 retrieved chunks（统一出口，含 source_id/chunk_id/text/metadata/score）
    # knowledge_block 由 retrieved_chunks 拼接而成，两者内容一致，允许 Answer 选择消费哪种
    retrieved_chunks: list[Any] = field(default_factory=list)  # list[RetrievedChunk]（用 Any 避免循环 import）

    # 主字段（Answer 默认从这些字段取材；knowledge_block/web_block 降为兼容辅助层）
    bundle_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    plan_id: str = ""
    execution_status: str = "ok"          # ok / partial / failed
    tool_calls: list[dict] = field(default_factory=list)
    temporary_materials: list[str] = field(default_factory=list)
    commit_results: list[dict] = field(default_factory=list)
    failures: list[dict] = field(default_factory=list)
    material_sufficiency: str = "sufficient"  # sufficient/insufficient/no_match/low_confidence
    evidence_envelopes: list[EvidenceEnvelope] = field(default_factory=list)

    # 视频 MCP 透传字段（默认值确保既有调用点零侵入）
    mcp_video_text: str | None = None
    mcp_video_source: str | None = None
    mcp_video_path: str | None = None
    mcp_video_ok: bool = False
    mcp_video_error: str = ""
    mcp_video_decision: str = "skip_no_video_yitu"
    # legacy-only：统一收口后，默认路径不再自动入库。
    # mcp_video_ingested / mcp_video_ingest_source_id / mcp_video_ingest_chunks 已退出默认路径；
    # 改用 mcp_video_pending_id 表达 pending 成功，不再用 "ingested" 表示 "pending"。
    mcp_video_ingested: bool = False                # legacy-only；已被 mcp_video_pending_id 替代
    mcp_video_ingest_source_id: str | None = None   # legacy-only
    mcp_video_ingest_chunks: int = 0                # legacy-only
    mcp_video_ingest_error: str = ""                # 沿用：prepare 阶段错误也写此字段
    # pending 成功后的 pending_id（替代旧 mcp_video_ingested 语义）
    mcp_video_pending_id: str | None = None         # MCP 视频 prepare/pending 成功后的 pending_id
    # 当前会话前文承接痕迹（middle 真用过 history 才会非默认）
    # - history_used        ：本轮 middle 是否真承接了 history.prev_video
    # - history_anchor_source_id：被沿用的上一轮入库锚点 source_id（形如 video:foo.mp4）
    # - history_followup_query  ：middle 用前文锚点拼出的检索 query（debug 用）
    # 默认值"零侵入"——既有断言完全不受影响。
    v8_history_used: bool = False
    v8_history_anchor_source_id: str | None = None
    v8_history_followup_query: str = ""
    # 连续追问可验收 / 失败边界 / 反假记忆。
    # - history_anchor_status：'fresh' 已承接且按 source_id 真命中
    #                          'stale' 承接到了锚点但 KB 里查无内容（锚点失效）
    #                          'none'  本轮未承接（无锚点 / 不指代 / 用户带新对象）
    # - history_anchor_stale ：便捷布尔——便于 service 端 extra 直接透传
    # 这两个字段是"诚实收口"的硬证据：当 stale 时，middle 不再回退到
    # 自然语言检索蒙答，而是把 cailiao_pan 走 que/ruo 路径，让 answer 抬升保守度。
    v8_history_anchor_status: str = "none"
    v8_history_anchor_stale: bool = False
    # 本轮 URL 链成功提取但**未入库**的视频文本，供 service 缓存到 session
    # 以便下一轮用户说「保存到知识库」时入库。
    v11_pending_video_text: object | None = None  # PendingVideoText（用 object 避免 import 环）
    # 本轮用户说「保存」后真的入库了 → service 需要回填 prev_video
    v11_saved_to_kb: bool = False
    v11_saved_source_id: str | None = None
    v11_saved_title: str | None = None

    # 统一 pending / commit 生命周期追踪字段
    # - pending_item         : 本轮 prepare 产出的 PendingKnowledgeItem（用 object 避免 import 环）
    # - v13_commit_result    : 本轮 commit_pending 的结果（CommitResult 或 None）
    # - v13_material_status  : temporary / pending / committed / failed（当前轮资料生命周期状态）
    # - v13_source_type      : 本轮资料来源类型（text / text_file / web_url）
    # - v13_used_pending_text: 是否本轮回答基于 pending 临时材料（非已入库 KB）
    pending_item: object | None = None             # PendingKnowledgeItem
    v13_commit_result: object | None = None        # CommitResult
    v13_material_status: str = ""                  # temporary / pending / committed / failed
    v13_source_type: str = ""
    v13_used_pending_text: bool = False
    # Middle 执行 Main.tool_plan 后的多来源结果。
    analysis_job: dict[str, Any] | None = None
    source_tasks: list[dict] = field(default_factory=list)
    source_briefs: list[dict] = field(default_factory=list)
    negotiation_trace: dict[str, Any] = field(default_factory=dict)
    comparison_matrix: dict[str, Any] | None = None
    critic_check: dict[str, Any] | None = None
    feedback_request: dict[str, Any] | None = None
    feedback_gate_result: dict[str, Any] | None = None
    round_delta: dict[str, Any] | None = None
    used_rounds: list[int] = field(default_factory=lambda: [0])
    final_answer_based_on_round: str = "round_0"
    used_context: list[str] = field(default_factory=list)
    answer_limitations: list[str] = field(default_factory=list)
    autonomy_loop_id: str = ""
    autonomy_events: list[dict[str, Any]] = field(default_factory=list)
    stop_reason: str = ""
    answer_check: str = "pass"
    revise_requested: bool = False
    retry_requested: bool = False
    more_evidence_requested: bool = False
    retry_count: int = 0
