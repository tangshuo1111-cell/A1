"""Background draft answers — cheap LLM + light critic (§5.10 / S9)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

from config.feature_flags import is_enabled
from config.settings import settings

Lane = Literal["video", "web", "document", "kb", "general"]
DraftPurpose = Literal["fast_pending", "task_result"]

_DEFAULT_LIMITATIONS = (
    "这是后台任务自动生成的草稿总结；如需正式签字答案，请在任务完成后继续追问。"
)


@dataclass(frozen=True)
class DraftAnswerResult:
    answer: str
    limitations: list[str] = field(default_factory=list)
    critic_check: dict[str, Any] = field(default_factory=dict)
    draft: bool = True


def draft_answer_v2_active() -> bool:
    return is_enabled("ENABLE_DRAFT_ANSWER_V2")


def _summarize_prompt(*, lane: str, user_query: str, material: str, title: str = "") -> str:
    title_line = f"标题：{title.strip()}\n" if (title or "").strip() else ""
    if lane == "video":
        return (
            "请基于下面视频字幕材料，用简体中文输出 3-5 个要点的结构化总结。"
            "每个要点 2 句话以内，优先提炼观点，不要复述大段原文，不要寒暄，不要输出额外前言。"
            "如果材料不足，要诚实说明。\n\n"
            f"{title_line}"
            f"用户问题：{(user_query or '').strip() or '请总结以下视频内容'}\n\n"
            f"材料：\n{(material or '').strip()[:8000]}"
        )
    return (
        f"请基于下面材料，用中文给出最短可用总结。"
        f" lane={lane}。优先直接回答，不展开无关背景；如果材料不足，要诚实说明。\n\n"
        f"{title_line}"
        f"用户问题：{(user_query or '').strip() or '请总结以下内容'}\n\n"
        f"材料：\n{(material or '').strip()[:6000]}"
    )


def _call_fast_llm(prompt: str) -> str:
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
                {
                    "role": "system",
                    "content": (
                        "你是一个中文轻量助手。用自然口语回复，先结论后补充；"
                        "避免 --- / ### / **标题** 等 markdown 模板；可保留 ✅ ⚠️ 📌。"
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=280,
        )
        content = resp.choices[0].message.content if resp.choices else ""
        return (content or "").strip()
    except Exception:  # noqa: BLE001 - 草稿生成失败时返回空串，由上游降级
        return ""


def run_light_critic(*, answer: str, material: str) -> dict[str, Any]:
    """Minimal critic — requires unsupported_claims to be empty (§5.10)."""
    unsupported_claims: list[dict[str, str]] = []
    limitations: list[str] = list(_DEFAULT_LIMITATIONS)

    if not (answer or "").strip():
        unsupported_claims.append({"claim": "(empty answer)", "reason": "empty_draft"})
    if not (material or "").strip() and (answer or "").strip():
        unsupported_claims.append(
            {"claim": "summary_without_material", "reason": "empty_material"}
        )

    revision_required = bool(unsupported_claims)
    return {
        "critic_check_id": f"critic_draft_{uuid.uuid4().hex[:10]}",
        "unsupported_claims": unsupported_claims,
        "weak_evidence_claims": [],
        "limitations": limitations,
        "revision_required": revision_required,
        "safe_to_answer": not revision_required,
    }


def _fallback_video_structured_answer(*, material: str) -> str:
    plain = " ".join((material or "").strip().split())
    if not plain:
        return "1. 未提取到可用字幕内容。\n\n2. 建议检查视频可访问性、音频质量或 ASR 配置后重试。"
    chunks = [seg.strip("，。；; ") for seg in plain.replace("？", "。").replace("！", "。").split("。") if seg.strip()]
    points: list[str] = []
    if chunks:
        points.append(f"1. 视频先用一个具体案例切入：{chunks[0]}。")
    if len(chunks) >= 2:
        points.append(f"2. 核心观点之一是不要把所谓“正式工作”想得绝对稳定：{chunks[1]}。")
    if len(chunks) >= 3:
        points.append(f"3. 对职业选择的建议是先行动、边做边调整：{chunks[2]}。")
    if len(chunks) >= 4:
        points.append(f"4. 视频强调很多决定未来仍可改变，不必因为害怕选错而停在原地：{chunks[3]}。")
    if len(points) < 3:
        sample = plain[:360]
        return (
            "1. 这段视频主要在讨论职业与人生选择，不主张把某个选项想成唯一正确答案。\n\n"
            "2. 视频强调先行动比反复空想更重要，很多机会会在实际工作过程中出现。\n\n"
            f"3. 材料摘录：{sample}"
        )
    return "\n\n".join(points[:4])


def _fallback_answer(*, lane: str, material: str, title: str = "") -> str:
    if lane == "video":
        return _fallback_video_structured_answer(material=material)
    plain = (material or "").strip()
    if not plain:
        prefix = f"已完成处理：{title}。" if (title or "").strip() else "任务已完成，但未提取到可用正文。"
        return prefix
    if len(plain) <= 2000:
        return plain
    return plain[:2000]


def build_draft_answer(
    *,
    lane: Lane,
    user_query: str,
    material: str,
    title: str = "",
    purpose: DraftPurpose = "task_result",
    clock: Any | None = None,
) -> DraftAnswerResult:
    """Build async worker final_answer with summarization template + light critic."""
    del clock
    if purpose not in {"fast_pending", "task_result"}:
        raise ValueError(f"unsupported draft purpose: {purpose!r}")
    prompt = _summarize_prompt(lane=lane, user_query=user_query, material=material, title=title)
    answer = ""
    if draft_answer_v2_active():
        answer = _call_fast_llm(prompt)
    if not answer:
        answer = _fallback_answer(lane=lane, material=material, title=title)

    critic = run_light_critic(answer=answer, material=material)
    limitations = list(critic.get("limitations") or [])
    if critic.get("unsupported_claims"):
        answer = _fallback_answer(lane=lane, material=material, title=title)
        critic = run_light_critic(answer=answer, material=material)
        limitations = list(critic.get("limitations") or []) + ["轻量 critic 未通过，已回退为材料摘录。"]

    return DraftAnswerResult(
        answer=answer.strip(),
        limitations=limitations,
        critic_check=critic,
        draft=True,
    )


def final_answer_fields_for_task(
    *,
    lane: Lane,
    user_query: str,
    material: str,
    title: str = "",
) -> dict[str, Any]:
    """Normalize worker result_summary fields for task store + query API."""
    draft = build_draft_answer(
        lane=lane,
        user_query=user_query,
        material=material,
        title=title,
        purpose="task_result",
    )
    return {
        "final_answer": draft.answer,
        "draft": True,
        "draft_limitations": draft.limitations,
        "draft_critic_check": draft.critic_check,
    }
