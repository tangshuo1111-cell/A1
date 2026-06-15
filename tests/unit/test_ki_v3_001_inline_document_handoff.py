from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agents.main_agent.schema import AgnoCollaborationPlan, MainXiezuoPan
from application.chat.inline_document_material import (
    extract_inline_document_from_message,
    promote_message_inline_document,
)
from application.chat.path_labels import resolve_complex_primary_path
from application.chat.pipeline.inline_document_plan_handoff import (
    apply_inline_document_plan_handoff,
)
from schemas import MainDecision

_CASE_MESSAGE = (
    "请基于下面这段文档内容，判断它适合放进项目面试讲解的哪一部分，并说明取舍："
    "本项目评测体系分为 route、exit state、capability chain、multi-turn state 和 agent collaboration 五层。"
)
_INLINE_BODY = (
    "本项目评测体系分为 route、exit state、capability chain、multi-turn state 和 agent collaboration 五层。"
)


def test_extract_inline_document_from_complex_document_reasoning_message() -> None:
    extracted = extract_inline_document_from_message(_CASE_MESSAGE)
    assert extracted == _INLINE_BODY


def test_promote_skips_url_tail_messages() -> None:
    web_kb_message = (
        "请结合知识库和这个网页，比较我的项目评测体系和 Python 官方教程这种文档型知识结构有什么不同："
        "https://docs.python.org/3/tutorial/index.html"
    )
    assert promote_message_inline_document(web_kb_message) is None


def test_promote_skips_when_upload_or_existing_text_content_present() -> None:
    assert promote_message_inline_document(_CASE_MESSAGE, existing_v13_text="already") is None
    assert promote_message_inline_document(_CASE_MESSAGE, existing_file_content=b"pdf") is None


def test_inline_document_plan_handoff_sets_prepare_text_and_temporary_material_mode() -> None:
    plan = AgnoCollaborationPlan(
        decision=MainDecision(task_id="t1", answer_channel="direct", need_rag=True),
        force_skip_evidence=False,
        web_supplement_mode="explicit_only",
        answer_composition="default",
        xiezuo_pan=MainXiezuoPan(
            renwu_lei="zhijie",
            zhengju_need=False,
            allow_kb=True,
            allow_web=False,
            fengxian_yinzi=0.2,
            celue_tag="zhijie",
        ),
        answer_mode="knowledge_grounded",
        needs_retrieval=True,
    )
    patched = apply_inline_document_plan_handoff(
        plan,
        v13_text_content=_INLINE_BODY,
        inline_document_promoted=True,
    )
    assert patched.v13_prepare_intent is None
    assert patched.answer_mode == "temporary_material"
    assert patched.needs_retrieval is False
    assert patched.needs_pending is False


@dataclass
class _BundleStub:
    temporary_materials: list[str] = field(default_factory=list)
    retrieved_chunks: list[Any] = field(default_factory=list)
    knowledge_block: str | None = None
    web_block: str | None = None
    kb_sufficiency_level: str = "none"
    v13_source_type: str = ""


def test_path_labels_prefers_document_complex_over_kb_chunks() -> None:
    bundle = _BundleStub(
        temporary_materials=["[inline_document]\ninline doc"],
        retrieved_chunks=[{"text": "kb benchmark"}],
        knowledge_block="kb benchmark",
    )
    assert resolve_complex_primary_path(bundle) == "document_complex"


def test_path_labels_still_marks_kb_when_no_document_material() -> None:
    bundle = _BundleStub(
        retrieved_chunks=[{"text": "kb benchmark"}],
        knowledge_block="kb benchmark",
    )
    assert resolve_complex_primary_path(bundle) == "agno_basic_v2_kb"
