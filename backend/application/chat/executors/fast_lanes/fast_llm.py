"""Shared fast-path LLM and summarization helpers."""

from __future__ import annotations

from config.settings import settings


def _needs_structured_fast_answer(message: str) -> bool:
    text = str(message or "").strip()
    if not text:
        return False
    lowered = text.lower()
    markers = (
        "3-5个要点",
        "3~5个要点",
        "3 到 5 个要点",
        "3到5个要点",
        "按 3-5 个要点",
        "按3-5个要点",
        "按3~5个要点",
        "按 3~5 个要点",
        "详细总结",
        "分点总结",
        "按要点",
        "要点总结",
        "结构化总结",
    )
    if any(marker in text for marker in markers):
        return True
    return ("要点" in text and ("总结" in text or "展开" in text)) or ("bullet" in lowered)


def _prefers_structured_web_summary(message: str) -> bool:
    text = str(message or "").strip()
    if not text:
        return False
    return any(
        marker in text
        for marker in ("这个网页讲了什么", "这个网页在讲什么", "总结这个网页", "总结一下这个网页", "这个链接讲了什么")
    )


def run_fast_llm_answer(
    message: str,
    *,
    context_block: str | None = None,
    system_prompt_override: str | None = None,
    max_tokens_override: int | None = None,
) -> str:
    prompt = (message or "").strip()
    if context_block:
        prompt = f"会话摘录：\n{context_block.strip()}\n\n当前用户消息：\n{prompt}"
    wants_structured = _needs_structured_fast_answer(message)
    system_prompt = "你是一个中文轻量助手。用最短可用答案回复，不展开，不寒暄过度。"
    max_tokens = 180
    if wants_structured:
        system_prompt = (
            "你是一个中文轻量助手。请按用户要求输出结构化结果，"
            "每点尽量 1-2 句，避免重复和寒暄，确保最后一条完整结束。"
        )
        max_tokens = 360
    if system_prompt_override:
        system_prompt = system_prompt_override
    if max_tokens_override is not None and max_tokens_override > 0:
        max_tokens = int(max_tokens_override)
    try:
        from openai import OpenAI

        client = OpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            timeout=min(float(settings.llm_timeout_seconds or 20.0), 20.0),
            max_retries=0,
        )
        resp = client.chat.completions.create(
            model=settings.fast_llm_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=max_tokens,
        )
        content = resp.choices[0].message.content if resp.choices else ""
        text = (content or "").strip()
        if text:
            return text
    except Exception:  # noqa: BLE001
        pass
    compact = (message or "").strip()
    if compact:
        return f"我可以继续帮你处理这个问题：{compact[:32]}。如果你愿意，我也可以继续展开。"
    return "我在。你可以继续把问题说得更具体一点。"


def summarize_fast_material(
    *,
    lane: str,
    message: str,
    material: str,
    context_block: str | None = None,
) -> str:
    prompt = (
        f"请基于下面材料，用中文给出最短可用首答。"
        f" lane={lane}。优先直接回答，不展开无关背景；如果材料不足，要诚实说明。\n\n"
        f"用户问题：{message.strip()}\n\n"
        f"材料：\n{(material or '').strip()[:6000]}"
    )
    system_prompt_override: str | None = None
    max_tokens_override: int | None = None
    if lane == "web" and "[网页正文]" in (material or ""):
        wants_web_points = _prefers_structured_web_summary(message) or _needs_structured_fast_answer(message)
        system_prompt_override = (
            "你是一个中文网页摘要助手。请基于网页正文直接回答用户问题，"
            + (
                "优先输出 3-5 个要点，每点 1-2 句，覆盖主题、关键事实、影响或结论；"
                if wants_web_points
                else "优先完整概括核心事实，可比默认快答稍微展开一点，但仍保持简洁；"
            )
            + "避免编造材料中没有的信息，确保最后一句完整结束。"
        )
        max_tokens_override = 520 if wants_web_points else 420
    return run_fast_llm_answer(
        prompt,
        context_block=context_block,
        system_prompt_override=system_prompt_override,
        max_tokens_override=max_tokens_override,
    )
