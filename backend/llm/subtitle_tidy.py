"""V11 R5 C：视频字幕入库前的"轻 LLM 梳理"。

设计边界（与 router.py 一脉相承）
---------------------------------
- **轻调用**：只调一次 OpenAI-compatible chat.completions，无重试嵌套
- **轻清理 ≠ 摘要**：prompt 严令 "保留全部信息，只修破碎句 / 明显错字"
  —— 不删段落、不归纳要点、不改语义；输出长度应与输入相近（容差 ±30%）
- **失败静默降级**：API 错 / 包不存在 / 输出疑似缩水 → **返回原文**，
  不抛异常给主链；同时返回结构化结果让 trace 能记录"为什么没用上"
- **超长跳过**：超过 ``settings.video_tidy_max_input_chars`` 直接返回原文
  （不做分段调用 —— 那属于 R5 之外的"chunked summarization"）
- **配置开关**：``settings.video_tidy_enabled`` False / 无 API Key → 直接 noop
- **零网络副作用**：单元测试通过 monkeypatch 替 ``OpenAI`` 即可隔离

返回 ``TidyResult`` 让 middle 知道"这次是 used / skipped / fallback"，
进而能写到 bundle.trace 给 answer 看到。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from config.settings import settings

logger = logging.getLogger("light_maqa")


@dataclass(frozen=True)
class TidyResult:
    """字幕梳理结果。

    - ``used``：True 即 ``text`` 是 LLM 梳理后的；False 即 ``text`` 是原文。
    - ``status``：用于 trace 的稳定字符串：
        * ``ok``         —— 梳理成功并采用
        * ``disabled``   —— ``video_tidy_enabled=False``，根本没调
        * ``no_api_key`` —— 缺 API Key，未调
        * ``too_long``   —— 输入超 max_chars，未调
        * ``empty``      —— 输入为空，未调
        * ``llm_error``  —— LLM 调用抛异常，降级原文
        * ``shrunk``     —— LLM 返回长度异常缩水，降级原文（防摘要化）
    - ``model``：实际使用的模型（仅 status=ok 时有值）。
    - ``in_chars`` / ``out_chars``：用于 trace 评估梳理"温柔程度"。
    """

    text: str
    used: bool
    status: str
    model: str = ""
    in_chars: int = 0
    out_chars: int = 0


_TIDY_SYSTEM_PROMPT = (
    "你是一个视频字幕排版助手。你的唯一任务：把破碎的字幕原文整理成可读的连续段落。\n"
    "硬性约束（违反任何一条都视为失败）：\n"
    "1. 严禁摘要、概括、归纳要点、提炼关键词。\n"
    "2. 严禁删除任何句子、人名、地名、数字、专有名词。\n"
    "3. 严禁加入字幕里没出现过的新信息或评论。\n"
    "4. 允许：合并被时间码切碎的半句；修明显错字（如『的得地』混用、ASR 同音字错字）；"
    "把同义重复的相邻句合并成一句；按内容自然分段。\n"
    "5. 输出应当与输入字数大致相当（容差 ±30%），如果你压缩超过 30% 视为违规失败。\n"
    "6. 直接输出整理后的纯文本，不要任何解释、不要 Markdown 标题、不要前缀后缀说明。"
)


def _shrink_too_much(in_chars: int, out_chars: int) -> bool:
    """防摘要化：输出比输入短超过 35% 就当作梳理违规（多给 5% 安全垫，
    避免合理"去重 + 修剪"被误杀）。"""
    if in_chars <= 0:
        return False
    return out_chars < int(in_chars * 0.65)


def tidy_subtitle(text: str, *, force: bool = False) -> TidyResult:
    """对一段字幕原文做"轻梳理"。

    入参：``text`` —— 已经过 ``url_fetch._strip_subtitle_markup`` 清洗的纯文本。
    ``force`` —— True 时跳过 ``video_tidy_enabled`` 检查（用户明确要求保存到知识库时强制梳理）。
    出参：``TidyResult`` —— 永远非 None；调用方按 ``used`` 决定用 text 替换原文。
    """
    raw = (text or "").strip()
    in_chars = len(raw)
    if not raw:
        return TidyResult(text="", used=False, status="empty", in_chars=0, out_chars=0)

    if not force and not settings.video_tidy_enabled:
        return TidyResult(text=raw, used=False, status="disabled", in_chars=in_chars, out_chars=in_chars)

    if not settings.openai_api_key:
        return TidyResult(text=raw, used=False, status="no_api_key", in_chars=in_chars, out_chars=in_chars)

    if in_chars > int(settings.video_tidy_max_input_chars or 0):
        return TidyResult(text=raw, used=False, status="too_long", in_chars=in_chars, out_chars=in_chars)

    try:
        from openai import OpenAI  # type: ignore[import-untyped]
    except ImportError:
        return TidyResult(text=raw, used=False, status="llm_error", in_chars=in_chars, out_chars=in_chars)

    model = (settings.video_tidy_model or "").strip() or settings.llm_router_model

    try:
        # V11 R5+ 修复：tidy 用**专用**短超时 + 不重试。
        # tidy 失败已经降级用原文（不影响入库 / 回答），但 retry 期间会**同步阻塞**
        # 整个 /chat/agno 请求；默认 llm 超时 60s × retry 2 次 → 最坏 180s，
        # 前端 fetch 早就超时报"服务器异常"了。专用配置：默认 30s + 0 retry，
        # "快失败、快降级"才对。
        client = OpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            timeout=settings.video_tidy_timeout_seconds,
            max_retries=settings.video_tidy_max_retries,
        )
        resp = client.chat.completions.create(
            model=model,
            temperature=0.1,
            messages=[
                {"role": "system", "content": _TIDY_SYSTEM_PROMPT},
                {"role": "user", "content": raw},
            ],
        )
        out = (resp.choices[0].message.content or "").strip()
    except Exception as e:  # noqa: BLE001
        logger.warning("v11r5c subtitle tidy llm_error model=%s err=%s", model, e)
        return TidyResult(text=raw, used=False, status="llm_error", in_chars=in_chars, out_chars=in_chars, model=model)

    out_chars = len(out)
    if not out:
        return TidyResult(text=raw, used=False, status="llm_error", in_chars=in_chars, out_chars=0, model=model)

    if _shrink_too_much(in_chars, out_chars):
        logger.warning(
            "v11r5c subtitle tidy shrunk model=%s in=%d out=%d (ratio=%.2f) -> fallback",
            model, in_chars, out_chars, out_chars / max(in_chars, 1),
        )
        return TidyResult(text=raw, used=False, status="shrunk", in_chars=in_chars, out_chars=out_chars, model=model)

    return TidyResult(text=out, used=True, status="ok", in_chars=in_chars, out_chars=out_chars, model=model)


__all__ = ["TidyResult", "tidy_subtitle"]
