"""
从一轮 ChatFlowResult 推导可观测字段：排查层、错误码、简短中文提示。
供 chat_service 注入 HTTP 响应与 extra，避免前端只能靠猜。
"""

from __future__ import annotations

from typing import Any

from schemas import ChatFlowResult, MainDecision


def interaction_mode_zh(decision: MainDecision, extra: dict[str, Any]) -> str:
    """用户可读的本轮模式标签（不暴露内部枚举名）。"""
    ch = (decision.answer_channel or "kb").strip().lower()
    channels = list(extra.get("channels_used") or [])
    if ch == "direct":
        return "直接对话（未查知识库）"
    if ch == "external":
        if "tool_http" in channels or "web_search" in channels:
            return "网页 / 外链"
        return "外链与抓取"
    if "tool_local" in channels and "rag" in channels:
        return "读了示例文件并查了知识库"
    if "tool_local" in channels:
        return "读了示例目录里的文件"
    if "rag" in channels:
        return "按知识库检索回答"
    return "按已有资料整理"

_PIPELINE_HINTS: dict[str, str] = {
    "KB_INIT_FAILED": "存储层：知识库初始化失败，请检查 data 目录与 SQLite 文件。",
    "MIDDLE_EXCEPTION": "编排层：资料收集（middle）抛错，查看日志中的 middle_agent。",
    "ANSWER_EXCEPTION": "回答层：answer 阶段异常，查看日志中的 answer_agent。",
    "ZERO_RAG_HIT": "检索层：知识库未命中（zero_rag_hit）。可换 README/demo 问法或执行 bootstrap。",
    "THIN_RAG_HIT": "检索层：命中偏弱（thin_rag_hit），结论仅供参考。",
    "URL_TOOL_FAILED": "工具层：外链/抓取失败，检查 URL 是否可访问或超时。",
    "LOCAL_FILE_FAILED": "工具层：本地示例文件读取失败，检查 knowledge_samples 路径。",
    "EXTERNAL_FETCH_EMPTY": "工具层：外链未取到有效正文。",
    "ROUTER_LLM_WARNING": "路由层：LLM 路由未生效或回退，见 decision.llm_error。",
}


def build_pipeline_observability(result: ChatFlowResult) -> dict[str, Any]:
    """
    返回顶层与 extra 共用的排查字段（不改变业务结果，只增加可观测性）。
    error_layer 取值与接管文档对齐：none | route | retrieval | tool | answer | storage | workflow
    """
    decision = result.decision
    answer = result.answer
    evidence = result.evidence
    gaps = list(evidence.gap_categories or []) if evidence else []
    ans_text = answer.final_answer or ""

    error_layer = "none"
    pipeline_error_code: str | None = None

    if "kb_init_failed" in gaps:
        error_layer = "storage"
        pipeline_error_code = "KB_INIT_FAILED"
    elif answer.answer_type == "error" or (
        answer.task_status == "failed" and "回答生成失败" in ans_text
    ):
        error_layer = "answer"
        pipeline_error_code = "ANSWER_EXCEPTION"
    elif "middle_exception" in gaps:
        error_layer = "workflow"
        pipeline_error_code = "MIDDLE_EXCEPTION"
    elif "url_tool_failed" in gaps:
        error_layer = "tool"
        pipeline_error_code = "URL_TOOL_FAILED"
    elif "local_file_failed" in gaps:
        error_layer = "tool"
        pipeline_error_code = "LOCAL_FILE_FAILED"
    elif (decision.llm_error or "").strip() and answer.task_status != "done":
        error_layer = "route"
        pipeline_error_code = "ROUTER_LLM_WARNING"
    elif "zero_rag_hit" in gaps and answer.task_status != "done":
        error_layer = "retrieval"
        pipeline_error_code = "ZERO_RAG_HIT"
    elif "thin_rag_hit" in gaps and answer.task_status != "done":
        error_layer = "retrieval"
        pipeline_error_code = "THIN_RAG_HIT"
    elif (
        (decision.answer_channel or "").strip().lower() == "external"
        and answer.task_status == "partial"
        and evidence
        and not any((e or "").strip() for e in evidence.evidence_list)
        and not any((e or "").strip() for e in evidence.key_evidence_list)
    ):
        error_layer = "tool"
        pipeline_error_code = "EXTERNAL_FETCH_EMPTY"

    pipeline_ok = answer.task_status == "done"

    hint = ""
    if pipeline_error_code:
        hint = _PIPELINE_HINTS.get(pipeline_error_code, "")

    extra_snap = dict(result.extra or {})
    mode = interaction_mode_zh(decision, extra_snap)

    return {
        "pipeline_ok": pipeline_ok,
        "debug_stage": "pipeline_completed",
        "error_layer": error_layer,
        "pipeline_error_code": pipeline_error_code,
        "pipeline_hint_zh": hint or None,
        "interaction_mode_zh": mode,
    }
