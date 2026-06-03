"""网页视频 ASR 时长策略：HTTP Chat 轮次内是否已确认「长视频走 ASR」。

由 ``agno_chat_service.run_agno_chat_turn`` 在入口 set/reset ContextVar；
``video.url_fetch.fetch_video_text`` / 工具链 ``extract_web_video_subtitle`` 在同一会话协程内读取。
"""

from __future__ import annotations

from contextvars import ContextVar

# True = 用户在本轮 POST /chat/agno 已显式确认（或前端携带 confirm_long_web_video_asr）
web_video_long_asr_confirmed: ContextVar[bool] = ContextVar(
    "web_video_long_asr_confirmed",
    default=False,
)
