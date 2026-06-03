"""
V8 第 1 轮：当前会话级历史记忆 —— 三强 Agent 主链共享的"前文承接对象"。

设计边界（写死、最小、不平台化）：
- 会话边界：以 `services.agno_chat_service` 已有的 session 级 deque 为唯一锚点；
  新 session（新 `session_id`）默认无快照 → 默认不继承。
  会话边界口径（统一）：当前版本以 `session_id` 作为当前会话边界的主实现；
  `thread_id` / `conversation_id` 仅作为兼容语义或未来扩展预留，不作为本轮额外
  完成要求；上游网关若要使用这两个名词，需在网关层映射成同一个 `session_id`
  再传入，本仓代码不直接消费这两个名字。
- 不引入新存储表、不引入新平台、不做跨会话长期记忆。
- 本对象只是把 service 已经持有的"前文原文"+"上一轮真实命中过的结构化锚点"打成一个
  **结构化承接容器**，向 Main / Middle / Answer 三方明确传入。
- 用结构化锚点（V7 视频入库 source_id）替代"prompt 关键词碰撞"，从源头降低
  V8 第 2 轮被做成假记忆的风险。

明确**不做**的事：
- 不做语义相似度记忆 / 不做向量索引；
- 不替 Main / Middle / Answer 出主判断核心字段（这是它们各自 runtime 的事）；
- 不直接调 LLM；
- 不直接读 SQLite —— 我们消费的"上一轮命中"由 service 在每轮产出时回填进 deque
  里附带的轻量元信息（in-memory），不动 storage 层。
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# 结构化"前一轮"锚点：V8 R1 优先承接 V7 视频链
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class PrevVideoRef:
    """上一轮真实跑过 video_to_text 入库链留下的结构化锚点。

    仅当 `mcp_video_ingested=True` 才会被 service 回填。
    """

    source_id: str           # 形如 "video:foo.mp4"，与 ingest 写入的 source_id 完全一致
    basename: str | None     # 形如 "foo.mp4"
    path: str | None         # 用户上一轮给的本地 .mp4 路径


@dataclass(frozen=True)
class PendingVideoText:
    """V11 R6：上一轮 URL 链成功提取但**尚未入库**的视频字幕文本。

    由 service 在 turn 末尾缓存到 session 内存，供下一轮用户说「保存到知识库」时入库。
    仅在内存中，不持久化。生命周期与 session 同步。
    """

    text: str
    title: str
    source_url: str
    source_basename: str
    duration_sec: float
    text_source: str          # "subtitle" | "asr"
    subtitle_lang: str | None = None
    asr_provider: str | None = None


# ---------------------------------------------------------------------------
# 指代识别：最小规则算子
# ---------------------------------------------------------------------------
# 仅用作"输入信号"，不替任何 agent 出主判断。
# 命中后是否真的承接，要看 history.has_prev_video 等结构化条件。
_FOLLOWUP_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"刚[才刚][那这]个?\s*(视频|内容|结果|文件|片段)?"),
    re.compile(r"上[一]?个?\s*(视频|内容|结果|回答|轮)"),
    re.compile(r"上[一]?次"),
    re.compile(r"那[条个]\s*(视频|内容|结果)?"),
    re.compile(r"这[条个]\s*(视频|内容|结果)?"),
    re.compile(r"继续\s*(说|讲|分析|回答|总结)?"),
    re.compile(r"接着\s*(说|讲|分析|回答|总结)?"),
    re.compile(r"再说\s*一?次?\s*(刚才|那个|这个)"),
)


def looks_like_followup_reference(message: str) -> bool:
    """是否像"承接前文 / 指代上一轮对象"的连续追问。

    仅做"显式信号"识别，不替 agent 出主判断；用于 Main / Middle 决定
    是否要把 `history.prev_video` 当承接锚点使用。
    """
    msg = (message or "").strip()
    if not msg:
        return False
    for pat in _FOLLOWUP_PATTERNS:  # noqa: SIM110
        if pat.search(msg):
            return True
    return False


# ---------------------------------------------------------------------------
# SessionHistorySnapshot：本轮入口由 service 一次性构造，传给三强 Agent
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class SessionHistorySnapshot:
    """当前会话前文 **结构化** 承接对象（V8 R1）。

    字段语义：
    - `session_id`：本轮所在的 session_id；空字符串视为 "__default__"。
    - `context_block`：service 已经拼好的多行"用户：xxx / 助手：yyy"前文文本，
       同时供 AnswerAgent 内部 LLM hint 使用（向后兼容旧 context_block 通路）。
    - `turns`：该会话已发生过的轮次数（不是 token 数 / 不是字符数）。
    - `prev_video`：上一轮真实通过 video_to_text 入库链留下的结构化锚点；
       为 None 表示该会话内尚未发生过视频入库（也包含"已发生但被显式清理"）。
    - `prev_kb_sources`：上一轮 service 透传出来的 V7 入库 source_id 集合，
       供未来扩展（V8 R1 仅用 prev_video 一项作首条联动锚点）。

    构造约束：
    - service 在 **每轮入口** 用 `from_history(...)` 构造一次；
    - 新 session 没有 deque → 自动得到一个"空快照"，从而保证新会话默认不继承。
    """

    session_id: str
    context_block: str
    turns: int
    prev_video: PrevVideoRef | None = None
    prev_kb_sources: tuple[str, ...] = field(default_factory=tuple)
    pending_video_text: PendingVideoText | None = None

    # ----- 便捷属性 -----
    @property
    def has_context(self) -> bool:
        """是否真有可承接的前文（既要有原文，也要有过完整轮次）。"""
        return bool((self.context_block or "").strip()) and self.turns > 0

    @property
    def has_prev_video(self) -> bool:
        return self.prev_video is not None

    def followup_video_anchor(self, message: str) -> PrevVideoRef | None:
        """当用户消息看起来在指代前文 **且** 上一轮存在视频入库锚点时，
        返回该锚点；否则 None。"""
        if not self.has_prev_video:
            return None
        if not looks_like_followup_reference(message):
            return None
        return self.prev_video

    # ----- 构造器（service 在每轮入口调）-----
    @classmethod
    def empty(cls, session_id: str | None) -> SessionHistorySnapshot:
        return cls(
            session_id=(session_id or "").strip() or "__default__",
            context_block="",
            turns=0,
            prev_video=None,
            prev_kb_sources=(),
        )

    @classmethod
    def from_history(
        cls,
        *,
        session_id: str | None,
        context_block: str | None,
        turns: int,
        prev_video: PrevVideoRef | None,
        prev_kb_sources: Iterable[str] | None = None,
        pending_video_text: PendingVideoText | None = None,
    ) -> SessionHistorySnapshot:
        return cls(
            session_id=(session_id or "").strip() or "__default__",
            context_block=(context_block or "").strip(),
            turns=int(turns),
            prev_video=prev_video,
            prev_kb_sources=tuple(prev_kb_sources or ()),
            pending_video_text=pending_video_text,
        )


# ---------------------------------------------------------------------------
# 公开 API
# ---------------------------------------------------------------------------
__all__ = [
    "PendingVideoText",
    "PrevVideoRef",
    "SessionHistorySnapshot",
    "looks_like_followup_reference",
]
