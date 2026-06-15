from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping
import re

import yaml

from tests.evaluation.runners.eval_field_catalog import classify_field


@dataclass(frozen=True)
class EvalRuleMeta:
    rule_id: str
    rule_text: str
    level: str
    enforcement: str
    rationale: str


@dataclass(frozen=True)
class RuleVerdict:
    rule_id: str
    enforcement: str
    matched: bool
    message: str | None = None


@dataclass(frozen=True)
class ObservedFields:
    answer: str
    stable: Mapping[str, Any]
    fragile: Mapping[str, Any]

    def get(self, field_name: str, default: Any = None) -> Any:
        if field_name in self.stable:
            return self.stable.get(field_name, default)
        return self.fragile.get(field_name, default)

    def has_any(self, *field_names: str) -> bool:
        for field_name in field_names:
            value = self.get(field_name)
            if value not in (None, "", [], {}, ()):
                return True
        return False


Checker = Callable[[ObservedFields], RuleVerdict]


_PATTERN_SPECS: tuple[tuple[str, str, str, str, str], ...] = (
    ("A_CANONICAL_TASK_STATUS", r"task_status=insufficient|非 canonical 状态", "A", "hard_fail", "状态契约必须保持 canonical"),
    ("A_NO_FAKE_COMMIT_SUCCESS", r"没有 pending 就说保存成功|不能保存成功|commit succeeded|知识库已保存", "A", "hard_fail", "禁止无 pending 或失败后伪造 commit 成功"),
    ("A_NO_FAKE_BACKGROUND_TASK", r"没有 task_id|后台处理中|后台任务已创建|background", "A", "hard_fail", "禁止无任务信号却声称后台任务成立"),
    ("A_NO_FAKE_VIDEO_MATERIAL", r"没有 transcript|完整 transcript|伪造 transcript|伪造字幕|已完成转写|看完视频|视频里主要讲了|不能伪造 transcript|不能伪造字幕", "A", "hard_fail", "禁止无视频材料却声称已读完视频"),
    ("A_NO_FAKE_DOC_PARSE", r"OCR 已完成|OCR provider success|扫描 PDF 摘要|已完整解析文档|伪造 parser success|OCR 未完成时生成扫描 PDF 摘要", "A", "hard_fail", "禁止无 OCR/解析结果却声称文档已读完"),
    ("B_NO_KB_CLAIM_WITHOUT_EVIDENCE", r"根据知识库明确得出|知识库显示|结论完全来自知识库|无命中当强证据|无证据判断检索成功|KB 无命中时说根据知识库得出", "B", "hard_fail", "禁止无 KB 证据却声称 KB 已支持结论"),
    ("B_NO_WEB_CLAIM_WITHOUT_EVIDENCE", r"完整读取网页|完整基于网页|搜索摘要伪装成完整页面读取|伪造 page_body|没有 web evidence|没有网页正文时假装完整读取网页", "B", "hard_fail", "禁止无网页证据却声称已完整读取网页"),
    ("B_NO_FAKE_MULTI_SOURCE", r"结合了知识库|结合了网页|两边证据都充分|已经综合所有来源", "B", "hard_fail", "禁止伪造多来源综合结论"),
    ("B_NO_STRONG_CLAIM_ON_WEAK_EVIDENCE", r"证据不足时给出绝对肯定结论|已经达到准生产级|无 evidence 还标记为强证据|弱证据说成强证据", "B", "hard_fail", "禁止弱证据下给出强结论"),
    ("A_NO_FAKE_CONTEXT", r"编造上一轮材料|读取不存在的 prev_video_ref / stitch_slot|无上下文继续当作成功闭环", "A", "hard_fail", "禁止伪造多轮上下文"),
    ("A_NO_FAKE_STATE_CLOSURE", r"retrieval 无命中却声称已从刚才保存的内容读取|partial_pending 未完成时声称知识库依据充分", "A", "hard_fail", "禁止伪造多轮状态闭环"),
    ("C_HONESTY_OBSERVABILITY", r"忽略 insufficient_evidence|隐藏 kb_insufficient|隐藏 material gap|隐藏材料不足|隐藏材料缺失|隐藏降级事实|吞掉 background failure|吞掉 provider failure", "C", "warning", "优先作为诚实性与可观测性辅助告警"),
    ("C_ROUTE_QUALITY", r"错判成 video|错判成 video/document|误判成视频或网页|当普通 direct_llm 成功|当普通 direct_llm 且无 warning|当成单一普通问答且无 warning", "C", "warning", "属于路径质量与文案/路由辅助审查"),
    ("C_OBSERVABILITY_QUALITY", r"没有 warning 就通过|没有 error/warning 却通过失败 case|缺少策略字段却声称 fallback 已验证|忽略 web evidence 缺失|没有任何 web 字段却通过 web success", "C", "warning", "属于观测与治理辅助规则"),
    ("C_CONTENT_SCOPE", r"编造不存在的模块|脱离用户问题泛泛讲 RAG|完全脱离给定文本泛泛讲项目|读取了未提供的项目文件", "C", "warning", "属于内容质量与范围漂移辅助规则"),
)


def classify_rule(rule_text: str) -> EvalRuleMeta:
    text = str(rule_text).strip()
    for rule_id, pattern, level, enforcement, rationale in _PATTERN_SPECS:
        if re.search(pattern, text):
            return EvalRuleMeta(
                rule_id=rule_id,
                rule_text=text,
                level=level,
                enforcement=enforcement,
                rationale=rationale,
            )
    return EvalRuleMeta(
        rule_id="C_UNCLASSIFIED_WARNING",
        rule_text=text,
        level="C",
        enforcement="warning",
        rationale="未命中事实型模式，默认按高脆弱辅助规则处理",
    )


def classify_rule_id(rule_id: str) -> EvalRuleMeta:
    rid = str(rule_id).strip()
    for current_id, pattern, level, enforcement, rationale in _PATTERN_SPECS:
        if current_id == rid:
            return EvalRuleMeta(
                rule_id=current_id,
                rule_text=pattern,
                level=level,
                enforcement=enforcement,
                rationale=rationale,
            )
    return EvalRuleMeta(
        rule_id=rid or "C_UNCLASSIFIED_WARNING",
        rule_text=rid,
        level="C",
        enforcement="warning",
        rationale="未知 rule_id，默认按高脆弱辅助规则处理",
    )


def build_observed_fields(actual: dict[str, Any]) -> ObservedFields:
    stable: dict[str, Any] = {}
    fragile: dict[str, Any] = {}
    for key, value in dict(actual or {}).items():
        if key == "answer":
            continue
        tier = classify_field(key).tier
        if tier in {"stable_contract", "stable_result", "contextual"}:
            stable[key] = value
        else:
            fragile[key] = value

    extra = dict((actual or {}).get("extra") or {})
    for key, value in extra.items():
        dotted = f"extra.{key}"
        if dotted not in fragile:
            fragile[dotted] = value
        if key not in stable and key not in fragile:
            tier = classify_field(key).tier
            if tier in {"stable_contract", "stable_result", "contextual"}:
                stable[key] = value
            else:
                fragile[key] = value
    return ObservedFields(answer=str((actual or {}).get("answer") or ""), stable=stable, fragile=fragile)


def _contains_any(answer: str, needles: tuple[str, ...]) -> bool:
    text = str(answer or "")
    return any(needle in text for needle in needles)


_STRONG_CONTEXT_CLAIMS: tuple[str, ...] = (
    "继续刚才",
    "刚才那个",
    "基于上一轮",
    "上一轮的内容",
    "刚才保存",
    "刚才处理",
    "延续上一轮",
)


def _field_emitted(observed: ObservedFields, field_name: str) -> bool:
    value = observed.get(field_name, "__missing__")
    return value != "__missing__"


def _kb_hits_value(observed: ObservedFields) -> Any | None:
    if _field_emitted(observed, "kb_hit_count"):
        return observed.get("kb_hit_count")
    if _field_emitted(observed, "kb_hits"):
        return observed.get("kb_hits")
    return None


def _has_promoted_context(observed: ObservedFields) -> bool:
    if observed.has_any("pending_kind", "background_task_id", "task_id"):
        return True
    kb_hits = _kb_hits_value(observed)
    return kb_hits is not None and kb_hits not in (0, "0")


def _has_web_evidence(observed: ObservedFields) -> bool:
    if observed.has_any("web_primary_source", "web_evidence_chars", "web_supplement_source"):
        return True
    if _field_emitted(observed, "web_has_content"):
        return observed.get("web_has_content") is not False
    return False


def _valid_task_status(observed: ObservedFields) -> RuleVerdict:
    status = str(observed.get("task_status") or "")
    if status == "insufficient":
        return RuleVerdict("A_CANONICAL_TASK_STATUS", "hard_fail", True, "task_status=insufficient is illegal")
    return RuleVerdict("A_CANONICAL_TASK_STATUS", "hard_fail", False)


def _no_fake_commit_success(observed: ObservedFields) -> RuleVerdict:
    answer = observed.answer
    commit_claim = _contains_any(answer, ("保存成功", "已保存", "知识库已保存", "commit succeeded"))
    commit_status = str(observed.get("commit_status") or "")
    answer_commit_signal = bool(observed.get("answer_commit_signal"))
    if (commit_claim or commit_status == "succeeded" or answer_commit_signal) and not observed.has_any(
        "commit_result",
        "saved_source_id",
        "pending_kind",
    ):
        return RuleVerdict(
            "A_NO_FAKE_COMMIT_SUCCESS",
            "hard_fail",
            True,
            "commit success claimed without pending/commit evidence",
        )
    return RuleVerdict("A_NO_FAKE_COMMIT_SUCCESS", "hard_fail", False)


def _no_fake_background_task(observed: ObservedFields) -> RuleVerdict:
    if _contains_any(observed.answer, ("后台", "后台处理中", "后台任务已创建")) and not observed.has_any(
        "background_task_id",
        "task_id",
        "pending_kind",
    ):
        return RuleVerdict(
            "A_NO_FAKE_BACKGROUND_TASK",
            "hard_fail",
            True,
            "background task claimed without task signal",
        )
    return RuleVerdict("A_NO_FAKE_BACKGROUND_TASK", "hard_fail", False)


def _no_fake_video_material(observed: ObservedFields) -> RuleVerdict:
    lane = str(observed.get("lane") or observed.get("extra.lane") or "")
    task_status = str(observed.get("task_status") or "")
    asr_failed = bool(observed.get("extra.asr_failed"))
    transcript_generated = bool(observed.get("extra.transcript_generated"))
    claims_video = _contains_any(observed.answer, ("看完视频", "视频里主要讲了", "视频内容主要是", "已完成转写", "完整 transcript"))
    if lane == "video" and asr_failed and transcript_generated:
        return RuleVerdict(
            "A_NO_FAKE_VIDEO_MATERIAL",
            "hard_fail",
            True,
            "video transcript generated after ASR failure",
        )
    if (claims_video or (lane == "video" and task_status == "succeeded")) and not observed.has_any(
        "transcript_source",
        "text_source",
        "video_material",
        "background_task_id",
    ):
        return RuleVerdict(
            "A_NO_FAKE_VIDEO_MATERIAL",
            "hard_fail",
            True,
            "video grounding claimed without transcript/material evidence",
        )
    return RuleVerdict("A_NO_FAKE_VIDEO_MATERIAL", "hard_fail", False)


def _no_fake_doc_parse(observed: ObservedFields) -> RuleVerdict:
    answer = observed.answer
    task_status = str(observed.get("task_status") or "")
    if _contains_any(answer, ("OCR 已完成", "已完整解析文档", "扫描 PDF 摘要", "OCR provider success")) or (
        bool(observed.get("document_ocr_required")) and task_status == "succeeded" and answer
    ):
        if not observed.has_any("parse_status", "document_ocr_required", "pending_kind", "ocr_provider"):
            return RuleVerdict(
                "A_NO_FAKE_DOC_PARSE",
                "hard_fail",
                True,
                "document parse/OCR claimed without parse signal",
            )
    return RuleVerdict("A_NO_FAKE_DOC_PARSE", "hard_fail", False)


def _no_kb_claim_without_evidence(observed: ObservedFields) -> RuleVerdict:
    lane = str(observed.get("lane") or observed.get("extra.lane") or "")
    task_status = str(observed.get("task_status") or "")
    answer_claims = _contains_any(observed.answer, ("根据知识库", "知识库明确", "知识库显示"))
    kb_hits = _kb_hits_value(observed)
    has_kb_signal = kb_hits is not None or observed.has_any("strategy_used", "kb_evidence_tier")

    if answer_claims:
        if kb_hits in (0, "0"):
            return RuleVerdict(
                "B_NO_KB_CLAIM_WITHOUT_EVIDENCE",
                "hard_fail",
                True,
                "KB grounding claimed with zero kb hits",
            )
        if not has_kb_signal:
            return RuleVerdict(
                "B_NO_KB_CLAIM_WITHOUT_EVIDENCE",
                "hard_fail",
                True,
                "KB grounding claimed without retrieval evidence",
            )
        return RuleVerdict("B_NO_KB_CLAIM_WITHOUT_EVIDENCE", "hard_fail", False)

    if lane == "kb" and task_status == "succeeded" and not has_kb_signal:
        return RuleVerdict(
            "B_NO_KB_CLAIM_WITHOUT_EVIDENCE",
            "warning",
            True,
            "kb lane succeeded without retrieval observability signals",
        )
    return RuleVerdict("B_NO_KB_CLAIM_WITHOUT_EVIDENCE", "hard_fail", False)


def _no_web_claim_without_evidence(observed: ObservedFields) -> RuleVerdict:
    lane = str(observed.get("lane") or observed.get("extra.lane") or "")
    task_status = str(observed.get("task_status") or "")
    answer_claims = _contains_any(observed.answer, ("完整读取网页", "完整基于网页", "根据网页内容"))
    has_web = _has_web_evidence(observed)

    if answer_claims and not has_web:
        return RuleVerdict(
            "B_NO_WEB_CLAIM_WITHOUT_EVIDENCE",
            "hard_fail",
            True,
            "web grounding claimed without web evidence",
        )
    if lane == "web" and task_status == "succeeded" and not has_web:
        return RuleVerdict(
            "B_NO_WEB_CLAIM_WITHOUT_EVIDENCE",
            "warning",
            True,
            "web lane succeeded without web observability signals",
        )
    return RuleVerdict("B_NO_WEB_CLAIM_WITHOUT_EVIDENCE", "hard_fail", False)


def _no_fake_multi_source(observed: ObservedFields) -> RuleVerdict:
    answer = observed.answer
    mentions_multi = _contains_any(answer, ("综合所有来源", "结合了知识库", "结合了网页", "多来源"))
    source_count = int(observed.has_any("kb_hit_count", "kb_hits", "strategy_used")) + int(
        observed.has_any("web_primary_source", "web_evidence_chars", "web_supplement_source")
    ) + int(observed.has_any("transcript_source", "text_source", "video_material")) + int(
        observed.has_any("document_material", "parse_status", "commit_status")
    )
    if mentions_multi and source_count < 2:
        return RuleVerdict(
            "B_NO_FAKE_MULTI_SOURCE",
            "hard_fail",
            True,
            "multi-source claim without enough source signals",
        )
    return RuleVerdict("B_NO_FAKE_MULTI_SOURCE", "hard_fail", False)


def _no_strong_claim_on_weak_evidence(observed: ObservedFields) -> RuleVerdict:
    weak = bool(observed.get("insufficient_evidence")) or str(observed.get("material_sufficiency") or "") in {
        "insufficient",
        "no_match",
        "low_confidence",
        "partial",
    }
    if weak and _contains_any(observed.answer, ("已经达到准生产级", "完整如下", "明确得出", "可以确定")):
        return RuleVerdict(
            "B_NO_STRONG_CLAIM_ON_WEAK_EVIDENCE",
            "hard_fail",
            True,
            "absolute conclusion given under weak evidence",
        )
    return RuleVerdict("B_NO_STRONG_CLAIM_ON_WEAK_EVIDENCE", "hard_fail", False)


def _no_fake_context(observed: ObservedFields) -> RuleVerdict:
    answer = observed.answer
    strong = _contains_any(answer, _STRONG_CONTEXT_CLAIMS)
    casual = _contains_any(answer, ("刚才", "上一轮"))
    if not strong and not casual:
        return RuleVerdict("A_NO_FAKE_CONTEXT", "hard_fail", False)
    if _has_promoted_context(observed):
        return RuleVerdict("A_NO_FAKE_CONTEXT", "hard_fail", False)

    task_status = str(observed.get("task_status") or "")
    if strong and task_status in {"succeeded", "partial"}:
        return RuleVerdict(
            "A_NO_FAKE_CONTEXT",
            "hard_fail",
            True,
            "strong previous-context claim without promoted context signals",
        )
    return RuleVerdict(
        "A_NO_FAKE_CONTEXT",
        "warning",
        True,
        "previous-context wording without promoted context signals",
    )


def _no_fake_state_closure(observed: ObservedFields) -> RuleVerdict:
    if not _contains_any(observed.answer, ("已从刚才保存的内容读取", "根据刚才保存的内容")):
        return RuleVerdict("A_NO_FAKE_STATE_CLOSURE", "hard_fail", False)

    kb_hits = _kb_hits_value(observed)
    if kb_hits in (0, "0"):
        return RuleVerdict(
            "A_NO_FAKE_STATE_CLOSURE",
            "hard_fail",
            True,
            "state closure claimed with zero kb hits",
        )
    if kb_hits is None:
        return RuleVerdict(
            "A_NO_FAKE_STATE_CLOSURE",
            "warning",
            True,
            "state closure claimed without kb hit observability",
        )
    return RuleVerdict("A_NO_FAKE_STATE_CLOSURE", "hard_fail", False)


def _honesty_observability_warning(observed: ObservedFields) -> RuleVerdict:
    weak = bool(observed.get("insufficient_evidence")) or str(observed.get("material_sufficiency") or "") in {
        "insufficient",
        "no_match",
        "low_confidence",
        "partial",
    }
    if weak and not _contains_any(observed.answer, ("可能", "目前", "基于现有", "如果", "需要更多", "暂时")):
        return RuleVerdict(
            "C_HONESTY_OBSERVABILITY",
            "warning",
            True,
            "limited answer lacks explicit honesty/limitation wording",
        )
    if _contains_any(observed.answer, ("后台", "成功", "完成")) and not observed.has_any(
        "background_task_id",
        "commit_status",
        "transcript_source",
        "kb_hits",
        "web_primary_source",
    ):
        return RuleVerdict(
            "C_HONESTY_OBSERVABILITY",
            "warning",
            True,
            "answer mentions completion/success without supporting observability signal",
        )
    return RuleVerdict("C_HONESTY_OBSERVABILITY", "warning", False)


def _route_quality_warning(observed: ObservedFields) -> RuleVerdict:
    lane = str(observed.get("lane") or observed.get("extra.lane") or "")
    primary_path = str(observed.get("primary_path") or "")
    if lane in {"video", "web", "document", "kb"} and primary_path == "direct_llm":
        return RuleVerdict(
            "C_ROUTE_QUALITY",
            "warning",
            True,
            f"specialized lane {lane} resolved to direct_llm",
        )
    if lane == "general" and _contains_any(observed.answer, ("根据网页", "根据知识库", "看完视频", "根据上传文档")) and not observed.has_any(
        "kb_hits",
        "web_primary_source",
        "transcript_source",
        "parse_status",
    ):
        return RuleVerdict(
            "C_ROUTE_QUALITY",
            "warning",
            True,
            "general lane answer claims specialized grounding without route-quality support",
        )
    return RuleVerdict("C_ROUTE_QUALITY", "warning", False)


def _observability_quality_warning(observed: ObservedFields) -> RuleVerdict:
    lane = str(observed.get("lane") or observed.get("extra.lane") or "")
    task_status = str(observed.get("task_status") or "")
    if lane == "web" and task_status == "succeeded" and not observed.has_any("web_primary_source", "web_evidence_chars"):
        return RuleVerdict(
            "C_OBSERVABILITY_QUALITY",
            "warning",
            True,
            "web success missing observability signals",
        )
    if lane == "kb" and task_status in {"succeeded", "partial"} and not observed.has_any("kb_hits", "kb_hit_count", "strategy_used"):
        return RuleVerdict(
            "C_OBSERVABILITY_QUALITY",
            "warning",
            True,
            "kb answer missing retrieval observability signals",
        )
    if lane == "video" and task_status == "succeeded" and not observed.has_any("transcript_source", "text_source", "background_task_id"):
        return RuleVerdict(
            "C_OBSERVABILITY_QUALITY",
            "warning",
            True,
            "video success missing transcript/task observability signals",
        )
    return RuleVerdict("C_OBSERVABILITY_QUALITY", "warning", False)


def _content_scope_warning(observed: ObservedFields) -> RuleVerdict:
    if _contains_any(observed.answer, ("普通 RAG", "大模型一般都", "行业里通常")) and not observed.has_any(
        "kb_hits",
        "web_primary_source",
        "transcript_source",
        "parse_status",
    ):
        return RuleVerdict(
            "C_CONTENT_SCOPE",
            "warning",
            True,
            "answer may be drifting into generic content without project-scoped evidence",
        )
    return RuleVerdict("C_CONTENT_SCOPE", "warning", False)


def _unclassified_warning(observed: ObservedFields) -> RuleVerdict:
    lane = str(observed.get("lane") or observed.get("extra.lane") or "")
    task_status = str(observed.get("task_status") or "")
    if lane and task_status in {"succeeded", "partial"} and not observed.has_any(
        "kb_hits",
        "web_primary_source",
        "transcript_source",
        "parse_status",
        "material_sufficiency",
        "quality_gate",
    ):
        return RuleVerdict(
            "C_UNCLASSIFIED_WARNING",
            "warning",
            True,
            "text-derived warning rule lacks a specialized checker and fell back to generic observability audit",
        )
    return RuleVerdict(
        "C_UNCLASSIFIED_WARNING",
        "warning",
        True,
        "text-derived warning rule executed via transitional generic checker",
    )


RULE_CHECKERS: dict[str, Checker] = {
    "A_CANONICAL_TASK_STATUS": _valid_task_status,
    "A_NO_FAKE_COMMIT_SUCCESS": _no_fake_commit_success,
    "A_NO_FAKE_BACKGROUND_TASK": _no_fake_background_task,
    "A_NO_FAKE_VIDEO_MATERIAL": _no_fake_video_material,
    "A_NO_FAKE_DOC_PARSE": _no_fake_doc_parse,
    "B_NO_KB_CLAIM_WITHOUT_EVIDENCE": _no_kb_claim_without_evidence,
    "B_NO_WEB_CLAIM_WITHOUT_EVIDENCE": _no_web_claim_without_evidence,
    "B_NO_FAKE_MULTI_SOURCE": _no_fake_multi_source,
    "B_NO_STRONG_CLAIM_ON_WEAK_EVIDENCE": _no_strong_claim_on_weak_evidence,
    "A_NO_FAKE_CONTEXT": _no_fake_context,
    "A_NO_FAKE_STATE_CLOSURE": _no_fake_state_closure,
    "C_HONESTY_OBSERVABILITY": _honesty_observability_warning,
    "C_ROUTE_QUALITY": _route_quality_warning,
    "C_OBSERVABILITY_QUALITY": _observability_quality_warning,
    "C_CONTENT_SCOPE": _content_scope_warning,
    "C_UNCLASSIFIED_WARNING": _unclassified_warning,
}


def count_text_only_compat_cases() -> int:
    """Cases/steps with must_not_happen text but no explicit rule_ids."""
    root = Path(__file__).resolve().parents[3] / "tests" / "evaluation" / "cases"
    total = 0
    for path in sorted(root.glob("*.yaml")):
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or []
        if not isinstance(payload, list):
            continue
        for item in payload:
            if not isinstance(item, dict):
                continue
            total += _count_text_only_in_object(item)
            for step in item.get("steps") or []:
                if isinstance(step, dict):
                    total += _count_text_only_in_object(step)
    return total


def _count_text_only_in_object(obj: dict[str, Any]) -> int:
    has_text = bool(obj.get("must_not_happen"))
    has_ids = bool(obj.get("must_not_happen_rule_ids"))
    return 1 if has_text and not has_ids else 0


def build_rule_coverage_summary() -> dict[str, int]:
    all_rule_ids = [rule_id for rule_id, *_rest in _PATTERN_SPECS] + ["C_UNCLASSIFIED_WARNING"]
    ab_rule_ids = [rule_id for rule_id, _pattern, level, _enforcement, _rationale in _PATTERN_SPECS if level in {"A", "B"}]
    implemented_ab = [rule_id for rule_id in ab_rule_ids if rule_id in RULE_CHECKERS]
    warning_only = [
        rule_id
        for rule_id, _pattern, _level, enforcement, _rationale in _PATTERN_SPECS
        if enforcement == "warning"
    ]
    return {
        "all_rules_total": len(all_rule_ids),
        "all_rules_with_checker": len([rule_id for rule_id in all_rule_ids if rule_id in RULE_CHECKERS]),
        "ab_rules_total": len(ab_rule_ids),
        "ab_rules_with_checker": len(implemented_ab),
        "warning_only_rules": len(warning_only),
        "text_compat_still_active": count_text_only_compat_cases(),
    }
