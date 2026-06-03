"""证据摘录转写与 KB / 外链 / 工具分支的正文拼装。"""

from __future__ import annotations

import re

from schemas import EvidencePack

from .answer_flow_direct import _asked_kb_inventory
from .prompt import _SECTION_GAP


def _pick_basis(evidence: EvidencePack) -> list[str]:
    if any((x or "").strip() for x in evidence.key_evidence_list):
        return [x for x in evidence.key_evidence_list if (x or "").strip()]
    return [x for x in evidence.evidence_list if (x or "").strip()]


def _evidence_to_user_bullets(items: list[str], style: str) -> list[str]:
    """把资料转写成短要点，控制长度，避免整段粘贴。"""
    bullets: list[str] = []
    for raw in items[:10]:
        t = raw.strip().replace("\n", " ")
        t = re.sub(r"\s+", " ", t)
        if len(t) < 12:
            continue
        if len(t) > 260:
            cut = t[:257]
            if "。" in cut[180:]:
                cut = cut[: cut.rindex("。", 0, 260)] + "。"
            else:
                cut = cut.rstrip("，、 ") + "…"
            t = cut
        if style == "steps" and len(bullets) < 6:
            prefix = f"{len(bullets) + 1}. "
        elif style == "compare":
            prefix = "· "
        else:
            prefix = "· "
        bullets.append(f"{prefix}{t}")
        if len(bullets) >= 4:
            break
    return bullets


def _compose_tool_local_failure() -> str:
    return (
        "本地示例文件这次没读成功：路径可能不在 knowledge_samples 目录、文件不存在，或不是 txt/md。"
        "请发类似 knowledge_samples/sample.md 的完整相对路径，我再试一次。"
    )


def _compose_tool_forward_answer(
    *,
    basis: list[str],
    style: str,
    had_rag: bool,
    time_note: str,
    coverage_low: bool,
    context_snippet: str,
) -> str:
    """工具（读文件）成功时：先交代读了文件，再列要点。"""
    bullets = _evidence_to_user_bullets(basis, style)
    if had_rag:
        lead = "先按你的要求读了示例文件，并对照知识库里相关片段，一起归纳如下："
    else:
        lead = "已读取你指定的示例文件，要点如下："
    tail_parts: list[str] = []
    if (context_snippet or "").strip():
        tail_parts.append("也参考了你刚才的对话上下文。")
    if time_note and "无" not in time_note[:4] and len(time_note) < 80:
        tail_parts.append(f"时效：{time_note}")
    if coverage_low:
        tail_parts.append("材料略零散，先帮你抓重点。")
    tail = " ".join(tail_parts) if tail_parts else "还要看别的段落随时说。"
    out = lead
    if bullets:
        out += _SECTION_GAP + "\n".join(bullets)
    out += _SECTION_GAP + tail
    return out.strip()


def _compose_web_search_answer(
    *,
    basis: list[str],
    style: str,
    time_note: str,
    coverage_low: bool,
    context_snippet: str,
) -> str:
    """公开网页检索有命中：明确交代来源是搜索摘要，不是知识库。"""
    bullets = _evidence_to_user_bullets(basis, style)
    lead = (
        "我刚按你的问题做了一轮公开网页检索（下面是摘要级要点，来自搜索结果，不是本站知识库；"
        "若要精确到实时气温/降雨，请以气象站点或官方 App 为准）："
    )
    tail_parts: list[str] = []
    if (context_snippet or "").strip():
        tail_parts.append("已结合近期对话理解你的指代。")
    if time_note and "无" not in time_note[:4] and len(time_note) < 80:
        tail_parts.append(f"时效：{time_note}")
    if coverage_low:
        tail_parts.append("摘要较零散，先列与问题最相关的几条。")
    tail = (
        " ".join(tail_parts)
        if tail_parts
        else "需要更准可以补充城市全称、区名或具体日期，或直接点开来源链接核对。"
    )
    out = lead
    if bullets:
        out += _SECTION_GAP + "\n".join(bullets)
    out += _SECTION_GAP + f"补充：{tail}"
    return out.strip()


def _compose_kb_style_answer(
    *,
    user_query: str,
    primary: str,
    style: str,
    channel: str,
    insufficient: bool,
    has_evidence: bool,
    basis: list[str],
    time_note: str,
    coverage_low: bool,
    context_snippet: str,
) -> str:
    """统一结构：一句话结论 + 2~4 条要点 + 补充说明。禁止输出内部路由/调试词。"""
    pg = (primary or "你的问题").strip()[:100]
    uq = (user_query or "").strip()
    inv = bool(uq and _asked_kb_inventory(uq))

    if insufficient and channel == "kb" and inv:
        lead = (
            "知识库里这次几乎没搜到成段的可用内容，可能还没导入文档，"
            "或说法和已入库文本差得比较远。"
        )
        bullets: list[str] = []
        tail = (
            "若刚搭好环境，可以先做一遍文档入库；"
            "再问时带着 README、sample 里常见的词，更容易命中。"
        )
    elif insufficient and channel == "kb":
        lead = f"我在当前项目知识库里没有找到和「{pg}」直接对得上的片段。"
        bullets = []
        tail = "可以换几个文档里出现过的关键词，或告诉我你想对照哪一节说明，我再帮你组织回答。"
    elif insufficient:
        lead = "就现有资料来看，信息还不够支撑一个稳妥、完整的结论。"
        bullets = []
        tail = "建议补充可访问的链接、文档片段，或把问题拆成更具体的小问。"
    elif not has_evidence:
        if channel == "external":
            lead = f"关于「{pg}」，外部渠道这次几乎没有可用的正文摘录。"
            bullets = []
            tail = "可以检查网络与链接是否可访问，或把页面里的关键段落贴过来。"
        else:
            lead = f"关于「{pg}」，本轮几乎没有可用的资料摘录，只能先给出框架性说明。"
            bullets = []
            tail = "若这是项目相关的问题，建议先确认知识库是否已导入对应文档。"
    elif channel == "kb" and inv:
        bullets = _evidence_to_user_bullets(basis, "general")
        lead = "从当前知识库能检索到的内容来看，大致包括下面这些信息（已帮你归纳，不是堆原文）："
        tail_parts: list[str] = []
        if (context_snippet or "").strip():
            tail_parts.append("已参考近期对话里的指代。")
        if coverage_low:
            tail_parts.append("命中略少，先把能确定的列给你。")
        tail = (
            " ".join(tail_parts)
            if tail_parts
            else "想展开某一条，可以说关键词或你想看的那一段。"
        )
    else:
        bullets = _evidence_to_user_bullets(basis, style)
        if style == "steps":
            lead = f"关于「{pg}」，建议按下面步骤理解（根据当前资料归纳，不是原文复制）："
        elif style == "compare":
            lead = f"关于「{pg}」，结合现有材料，可以从这些角度对照："
        elif style == "conclusion":
            lead = f"关于「{pg}」，先给结论：结合现有资料，核心判断是——"
        elif style == "explain":
            lead = f"关于「{pg}」，用现有资料可以这样理解："
        else:
            if channel == "external":
                lead = f"根据目前拿到的外部内容（网页抓取或检索摘要），「{pg}」可以先概括为——"
            else:
                lead = f"结论先说：结合知识库里的材料，「{pg}」可以概括为——"
        tail_parts = []
        if (context_snippet or "").strip():
            tail_parts.append("已参考近期对话内容理解你的指代。")
        if time_note and "无" not in time_note[:4] and len(time_note) < 80:
            tail_parts.append(f"时效方面：{time_note}")
        if coverage_low:
            tail_parts.append("材料覆盖有限，请把结论当作参考而非最终定论。")
        tail = " ".join(tail_parts) if tail_parts else "如需更细，可以指出想深入的一小段。"

    out = lead
    if bullets:
        out += _SECTION_GAP + "\n".join(bullets)
    out += _SECTION_GAP + f"补充：{tail}"
    return out.strip()
