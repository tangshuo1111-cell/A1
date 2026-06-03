"""Document summarize orchestration — fast lane 首答摘要。"""

from __future__ import annotations

from config.settings import settings

_DOCUMENT_SUMMARIZE_TIMEOUT_SECONDS = 35.0


def _needs_structured_document_answer(message: str) -> bool:
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


def _prefers_default_document_summary(message: str) -> bool:
    text = str(message or "").strip()
    if not text:
        return False
    markers = (
        "这个文档讲了什么",
        "这个文件讲了什么",
        "总结这个文档",
        "总结一下这个文档",
        "总结这个文件",
        "总结一下这个文件",
        "概括这个文档",
        "概括这个文件",
    )
    return any(marker in text for marker in markers)


def summarize_document(
    *,
    message: str,
    material: str,
    context_block: str | None = None,
) -> str:
    prompt = (
        "请基于下面材料，用中文给出最短可用首答。"
        " lane=document。优先直接回答，不展开无关背景；如果材料不足，要诚实说明。\n\n"
        f"用户问题：{(message or '').strip()}\n\n"
        f"材料：\n{(material or '').strip()[:6000]}"
    )
    if context_block:
        prompt = f"会话摘录：\n{context_block.strip()}\n\n{prompt}"
    wants_structured = _needs_structured_document_answer(message) or _prefers_default_document_summary(message)
    system_prompt = "你是一个中文轻量助手。用最短可用答案回复，不展开，不寒暄过度。"
    max_tokens = 180
    if wants_structured:
        prompt = (
            "请基于下面材料，用中文输出 3-5 个编号要点。"
            "每个要点 1-2 句，优先覆盖主题、关键功能/内容、调用或使用条件、限制或结论；"
            "不要写成长段落，不要寒暄，最后一条必须完整结束。\n\n"
            f"用户问题：{(message or '').strip()}\n\n"
            f"材料：\n{(material or '').strip()[:6000]}"
        )
        if context_block:
            prompt = f"会话摘录：\n{context_block.strip()}\n\n{prompt}"
        system_prompt = (
            "你是一个中文文档摘要助手。请优先输出 3-5 个要点，"
            "每点尽量 1-2 句，覆盖主题、关键内容和结论或用途，避免重复和寒暄，确保最后一条完整结束。"
        )
        max_tokens = 720
    try:
        from openai import OpenAI

        client = OpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            timeout=max(
                min(float(settings.llm_timeout_seconds or 20.0), _DOCUMENT_SUMMARIZE_TIMEOUT_SECONDS),
                _DOCUMENT_SUMMARIZE_TIMEOUT_SECONDS,
            ),
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
    except Exception:  # noqa: BLE001 - 摘要 LLM 失败时回退到模板提示
        pass
    compact = (message or "").strip()
    if compact:
        return f"我可以继续帮你处理这个问题：{compact[:32]}。如果你愿意，我也可以继续展开。"
    return "我在。你可以继续把问题说得更具体一点。"
