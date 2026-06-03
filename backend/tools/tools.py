"""
普通 Function Call 工具注册与调用壳子。

分层实现位于 tools/search、tools/fetch、tools/api；本文件聚合注册，保持 call(name) 入口稳定。
"""

from __future__ import annotations

import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

from config.settings import settings
from tools.api.http_get import http_get_tool
from tools.fetch.html_text import extract_readable_text
from tools.search.web_search import web_search_tool

# 工具名 -> 可调用对象
_REGISTRY: dict[str, Callable[..., Any]] = {}


def register(name: str, fn: Callable[..., Any]) -> None:
    """注册工具。"""
    _REGISTRY[name] = fn


def list_tools() -> list[str]:
    """列出已注册工具名。"""
    return list(_REGISTRY.keys())


def call(name: str, **kwargs: Any) -> Any:
    """按名称调用工具；未注册则抛错。"""
    if not settings.enable_tools:
        raise RuntimeError("ENABLE_TOOLS=0，工具调用已关闭")
    if name not in _REGISTRY:
        raise NotImplementedError(f"工具未注册: {name}")
    from observability import metrics_record_tool_call

    try:
        out = _REGISTRY[name](**kwargs)
    except Exception:  # noqa: BLE001 — 工具实现任意异常：仅记指标后原样抛出
        metrics_record_tool_call(name, False)
        raise
    ok = True
    if isinstance(out, dict) and "ok" in out:
        ok = bool(out.get("ok"))
    metrics_record_tool_call(name, ok)
    return out


def fetch_url(
    url: str,
    timeout: float | None = None,
    max_bytes: int = 80_000,
) -> dict[str, Any]:
    """
    拉取 HTTP(S) 页面正文（极简）。
    返回 {"ok": bool, "text"?: str, "error"?: str}
    默认超时来自环境变量 HTTP_FETCH_TIMEOUT_SEC（config.settings）。
    """
    t = timeout if timeout is not None else settings.http_fetch_timeout_sec
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "LightMultiAgentQA/1.0 (skeleton)"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=t) as resp:
            raw = resp.read(max_bytes)
        text = raw.decode("utf-8", errors="replace")
        simplified = extract_readable_text(text, max_chars=8000)
        return {"ok": True, "text": simplified}
    except (urllib.error.URLError, OSError, ValueError) as e:
        return {"ok": False, "error": str(e)}


def read_text_file(rel_path: str) -> dict[str, Any]:
    """
    读取 knowledge_samples 目录下的 txt/md（路径穿越防护）。
    rel_path 可为 'sample.md' 或 'knowledge_samples/sample.md'（会规范到沙箱内）。
    """
    root = settings.knowledge_samples_dir().resolve()
    root.mkdir(parents=True, exist_ok=True)
    raw = rel_path.strip().replace("\\", "/")
    if raw.lower().startswith("knowledge_samples/"):
        raw = raw.split("/", 1)[1]
    candidate = (root / raw).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return {"ok": False, "error": "路径必须位于 knowledge_samples 目录内"}
    if not candidate.is_file():
        return {"ok": False, "error": f"文件不存在: {candidate.name}"}
    if candidate.suffix.lower() not in {".txt", ".md"}:
        return {"ok": False, "error": "仅允许读取 .txt / .md"}
    text = candidate.read_text(encoding="utf-8", errors="replace")
    return {
        "ok": True,
        "path": str(candidate.relative_to(settings.project_root)),
        "text": text[:12_000],
    }


def list_knowledge_sample_files() -> dict[str, Any]:
    """列出预置示例目录下全部 txt/md（相对 project_root 的路径）。"""
    root = settings.knowledge_samples_dir().resolve()
    root.mkdir(parents=True, exist_ok=True)
    pr = settings.project_root.resolve()
    files: list[str] = []
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.suffix.lower() in {".txt", ".md"}:
            files.append(str(p.resolve().relative_to(pr)).replace("\\", "/"))
    return {"ok": True, "files": files}


def _register_builtins() -> None:
    register("fetch_url", fetch_url)
    register("read_text_file", read_text_file)
    register("list_knowledge_sample_files", list_knowledge_sample_files)
    register("web_search", web_search_tool)
    register("http_get", http_get_tool)


_register_builtins()
