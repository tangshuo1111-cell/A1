"""Middle Agent 复杂链 smoke：逐题 POST /chat/agno，记录耗时与 trace 摘要。"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

BASE = "http://127.0.0.1:8000"
OUT_DIR = Path("_local/middle_agent_smoke")
TIMEOUT_S = 180


@dataclass
class Case:
    id: str
    category: str
    message: str = ""
    use_knowledge: bool = False
    upload_path: str | None = None
    upload_message: str | None = None
    confirm_long_web_video_asr: bool = False


@dataclass
class Result:
    case_id: str
    category: str
    session_id: str
    elapsed_s: float
    ok: bool
    error: str = ""
    answer_len: int = 0
    answer_preview: str = ""
    lane: str = ""
    mode: str = ""
    executor_profile: str = ""
    fast_path: str = ""
    tool_calls: list[str] = field(default_factory=list)
    capabilities_called: list[str] = field(default_factory=list)
    quality_notes: list[str] = field(default_factory=list)
    responsiveness: str = ""


CASES: list[Case] = [
    Case(
        id="T1",
        category="web_search+fetch",
        message=(
            "请搜索「Apifox 和 Postman 2025 差异」，阅读前 2 篇结果页面，"
            "从 API 设计、协作、Mock、测试四个维度对比，并给出适用场景建议。"
        ),
    ),
    Case(
        id="T2",
        category="web_search+fetch",
        message=(
            "联网搜一下「RAG hybrid retrieval best practices」，"
            "读 1～2 个网页，总结 keyword 和 semantic 怎么配合，证据不足要说明。"
        ),
    ),
    Case(
        id="T3",
        category="multi_url_compare",
        message=(
            "请对比这两个页面在「产品定位」上的异同，并综合给出结论：\n"
            "https://docs.apifox.com/introduction\n"
            "https://www.postman.com/product/what-is-postman/"
        ),
    ),
    Case(
        id="T4",
        category="kb+web",
        use_knowledge=True,
        message=(
            "结合知识库和网页证据，综合评估我们文档里对 RAG hybrid 混合检索"
            "（keyword 与 semantic 如何配合、alpha 权重）的描述，是否与 "
            "https://en.wikipedia.org/wiki/Retrieval-augmented_generation "
            "的说法一致，列出一致点和冲突点。"
        ),
    ),
    Case(
        id="T5",
        category="document_parse",
        upload_path="tests/fixtures/v16_materials/pdf_text/sample_text.pdf",
        upload_message=(
            "我上传了一个 sample_text.pdf，请先解析这份文档，按章节提取要点，"
            "并和知识库里相关条目对比，给出差异摘要。"
        ),
        use_knowledge=True,
    ),
    Case(
        id="T6",
        category="ocr",
        upload_path="tests/fixtures/v16_materials/pdf_scanned/sample_scanned_like.pdf",
        upload_message=(
            "我上传了一个扫描版 sample_scanned_like.pdf，请先解析这份文档（扫描件需 OCR），"
            "按章节提取重点，再总结成三条结论。"
        ),
    ),
    Case(
        id="T7",
        category="video",
        confirm_long_web_video_asr=True,
        message=(
            "请提取这个视频的字幕/内容，并总结其中关于 API 测试的 5 个要点："
            "https://www.bilibili.com/video/BV1xx411c7mD"
        ),
    ),
    Case(
        id="T8",
        category="dynamic_web",
        message=(
            "请综合对比分析：这个 Angular 官方页需要动态渲染才能读到正文。"
            "抓取 https://angular.io/guide/what-is-angular 的核心说明，"
            "并从框架定位、上手成本两个维度给出要点与异同。"
        ),
    ),
    Case(
        id="T9",
        category="complex_reasoning_only",
        message=(
            "请比较 Cursor、Windsurf、Codex 三类 AI coding assistant，"
            "从定位、工作流、适合人群、潜在风险四个维度分析。"
        ),
    ),
]


def _post_json(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _post_multipart(
    path: str,
    *,
    message: str,
    session_id: str,
    use_knowledge: bool,
    file_path: Path,
) -> dict[str, Any]:
    import mimetypes

    boundary = "----MiddleAgentSmokeBoundary7MA4YWxk"
    file_bytes = file_path.read_bytes()
    filename = file_path.name
    mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"

    parts: list[bytes] = []
    for name, value in (
        ("message", message),
        ("session_id", session_id),
        ("use_knowledge", "true" if use_knowledge else "false"),
    ):
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()
        )
    parts.append(
        (
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            f"Content-Type: {mime}\r\n\r\n"
        ).encode()
        + file_bytes
        + b"\r\n"
    )
    parts.append(f"--{boundary}--\r\n".encode())
    body = b"".join(parts)

    req = urllib.request.Request(
        f"{BASE}{path}",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _extract_tool_names(extra: dict[str, Any]) -> list[str]:
    """统一从 v15_tool_calls / capabilities_called / tool_calls 读工具名（去重保序）。"""
    names: list[str] = []

    def _add(name: str) -> None:
        n = (name or "").strip()
        if n and n not in names:
            names.append(n)

    for item in extra.get("v15_tool_calls") or []:
        if isinstance(item, dict):
            _add(str(item.get("tool") or item.get("tool_name") or ""))
        else:
            _add(str(item or ""))
    for cap in extra.get("capabilities_called") or []:
        _add(str(cap or ""))
    for item in extra.get("tool_calls") or []:
        if isinstance(item, dict):
            _add(str(item.get("tool") or item.get("tool_name") or ""))
    for item in extra.get("middle_tool_steps") or []:
        if isinstance(item, dict):
            _add(str(item.get("tool_name") or item.get("tool") or ""))
    return names


def _assess(case: Case, extra: dict[str, Any], answer: str) -> tuple[list[str], str]:
    notes: list[str] = []
    fp = str(extra.get("fast_path") or "")
    profile = str(extra.get("executor_profile") or extra.get("profile") or "")
    mode = str(extra.get("mode") or "")
    tools = _extract_tool_names(extra)

    if case.category == "complex_reasoning_only":
        if fp:
            notes.append(f"走了 fast_path={fp}，预期 complex 纯推理")
        elif profile == "complex" or mode == "complex":
            notes.append("进入 complex 主链")
        else:
            notes.append(f"profile/mode={profile}/{mode}")
        if tools:
            notes.append(f"意外调工具: {tools}")
        else:
            notes.append("未调工具（符合预期）")
    else:
        if fp in {"web_fast_fulltext", "kb_fast", "general_fast"}:
            notes.append(f"⚠ 误走 fast_path={fp}")
        if profile == "complex" or mode == "complex":
            notes.append("进入 complex")
        elif fp:
            notes.append(f"fast 路径: {fp}")
        if tools:
            notes.append(f"工具: {', '.join(dict.fromkeys(tools))}")
        else:
            notes.append("⚠ trace 中未见 tool_calls")

    if len(answer.strip()) < 120:
        notes.append("⚠ 回答过短")
    elif len(answer.strip()) > 800:
        notes.append("回答篇幅充足")
    else:
        notes.append("回答中等长度")

    if "temporary_materials 为空" in answer or "没有可用" in answer:
        notes.append("⚠ 材料为空类失败话术")

    if extra.get("error_code") or extra.get("failure_reason"):
        notes.append(f"错误: {extra.get('error_code') or extra.get('failure_reason')}")

    elapsed_hint = "响应正常" if len(answer) > 0 else "无有效回答"
    return notes, elapsed_hint


def _poll_task_if_any(data: dict[str, Any], *, max_wait_s: int = 60, interval_s: float = 4.0) -> str:
    """若返回带后台 task_id（如视频 ASR background），轮询 GET /tasks/{id} 直到结束。"""
    task_id = str(data.get("task_id") or "").strip()
    if not task_id:
        extra = data.get("extra") or {}
        task_id = str(extra.get("background_task_id") or extra.get("v16_background_task_id") or "").strip()
    if not task_id:
        return ""
    deadline = time.perf_counter() + max_wait_s
    last_status = ""
    while time.perf_counter() < deadline:
        try:
            req = urllib.request.Request(f"{BASE}/tasks/{task_id}", method="GET")
            with urllib.request.urlopen(req, timeout=20) as resp:
                tj = json.loads(resp.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            return f"task轮询异常({task_id[:8]}): {type(e).__name__}"
        last_status = str(tj.get("status") or "")
        if last_status in {"succeeded", "failed", "error", "done", "completed"}:
            txt_len = len(str((tj.get("result") or {}).get("text") or tj.get("text") or ""))
            return f"task={task_id[:8]} status={last_status} text_len={txt_len}"
        time.sleep(interval_s)
    return f"task={task_id[:8]} status={last_status or 'pending'}(超时未完成)"


def run_case(case: Case) -> Result:
    session_id = f"middle-smoke-{case.id.lower()}"
    t0 = time.perf_counter()
    try:
        if case.upload_path:
            data = _post_multipart(
                "/chat/agno/upload",
                message=case.upload_message or case.message,
                session_id=session_id,
                use_knowledge=case.use_knowledge,
                file_path=Path(case.upload_path),
            )
        else:
            data = _post_json(
                "/chat/agno",
                {
                    "message": case.message,
                    "session_id": session_id,
                    "use_knowledge": case.use_knowledge,
                    "confirm_long_web_video_asr": case.confirm_long_web_video_asr,
                },
            )
        elapsed = time.perf_counter() - t0
        extra = data.get("extra") or {}
        answer = str(data.get("answer") or "")
        task_note = _poll_task_if_any(data)
        notes, responsiveness = _assess(case, extra, answer)
        if task_note:
            notes.append(task_note)
        return Result(
            case_id=case.id,
            category=case.category,
            session_id=session_id,
            elapsed_s=round(elapsed, 2),
            ok=bool(data.get("ok", True)),
            answer_len=len(answer),
            answer_preview=answer[:500].replace("\r", ""),
            lane=str(extra.get("lane") or extra.get("router_lane") or ""),
            mode=str(extra.get("mode") or ""),
            executor_profile=str(extra.get("executor_profile") or extra.get("profile") or ""),
            fast_path=str(extra.get("fast_path") or ""),
            tool_calls=_extract_tool_names(extra),
            capabilities_called=[str(x) for x in (extra.get("capabilities_called") or [])],
            quality_notes=notes,
            responsiveness=responsiveness,
        )
    except Exception as e:  # noqa: BLE001
        elapsed = time.perf_counter() - t0
        return Result(
            case_id=case.id,
            category=case.category,
            session_id=session_id,
            elapsed_s=round(elapsed, 2),
            ok=False,
            error=f"{type(e).__name__}: {e}",
            quality_notes=["请求失败"],
            responsiveness="失败",
        )


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    results = [run_case(c) for c in CASES]
    total_s = round(sum(r.elapsed_s for r in results), 2)
    payload = {
        "total_elapsed_s": total_s,
        "case_count": len(results),
        "results": [asdict(r) for r in results],
    }
    json_path = OUT_DIR / "middle_agent_smoke_latest.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Middle Agent Smoke 报告",
        "",
        f"- 总耗时: **{total_s}s**（{len(results)} 题）",
        f"- 时间: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "| ID | 类别 | session | 耗时(s) | profile/mode | fast_path | 工具 | 质量摘要 | 错误 |",
        "|----|------|---------|--------|--------------|-----------|------|----------|------|",
    ]
    for r in results:
        tools = ", ".join(dict.fromkeys(r.tool_calls)) or "-"
        notes = "; ".join(r.quality_notes[:3])
        err = r.error or "-"
        lines.append(
            f"| {r.case_id} | {r.category} | `{r.session_id}` | {r.elapsed_s} | "
            f"{r.executor_profile or r.mode or '-'} | {r.fast_path or '-'} | {tools} | {notes} | {err} |"
        )
    lines.append("")
    lines.append("## 各题回答预览")
    lines.append("")
    for r in results:
        lines.extend(
            [
                f"### {r.case_id} — {r.category}",
                f"- session: `{r.session_id}`",
                f"- 耗时: {r.elapsed_s}s · 字数: {r.answer_len}",
                f"- lane/mode/fast: {r.lane}/{r.mode}/{r.fast_path or '-'}",
                f"- 工具: {', '.join(r.tool_calls) or '无'}",
                f"- 备注: {'; '.join(r.quality_notes)}",
                "",
                "```",
                (r.answer_preview + ("…" if r.answer_len > 500 else "")),
                "```",
                "",
            ]
        )
    md_path = OUT_DIR / "middle_agent_smoke_latest.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"total_elapsed_s": total_s, "json": str(json_path), "md": str(md_path)}, ensure_ascii=False))
    for r in results:
        print(f"{r.case_id} {r.elapsed_s}s ok={r.ok} tools={r.tool_calls} fp={r.fast_path}")


if __name__ == "__main__":
    main()
