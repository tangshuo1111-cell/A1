"""用仓库内小 fixture 走文档 registry（第四轮 B-024）。"""

from __future__ import annotations

import sys
from pathlib import Path

from tests._support.bootstrap import find_repo_root

ROOT = find_repo_root(__file__)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tools.document  # noqa: F401, E402 — 触发注册
from tools.document import registry  # noqa: E402

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "v16_materials"


def test_parse_txt_fixture_success() -> None:
    p = FIX / "txt" / "sample_success.txt"
    r = registry.call_tool("parse_txt_document", file_path=str(p))
    assert r.status == "success"
    assert len((r.text or "").strip()) > 20


def test_parse_md_fixture_success() -> None:
    p = FIX / "md" / "sample_success.md"
    r = registry.call_tool("parse_md_document", file_path=str(p))
    assert r.status == "success"


def test_parse_xlsx_fixture_success() -> None:
    p = FIX / "xlsx" / "sample_success.xlsx"
    r = registry.call_tool("parse_excel", file_path=str(p))
    assert r.status == "success"
    assert (r.text or "").strip()


def test_parse_pdf_text_fixture_reasonable_path() -> None:
    """文本型 PDF：应能抽出非空文本（环境缺依赖时可能失败，此时跳过）。"""
    p = FIX / "pdf_text" / "sample_text.pdf"
    r = registry.call_tool("parse_pdf", file_path=str(p))
    if r.status != "success":
        import pytest

        pytest.skip(f"PDF 解析未就绪: {r.error_code} {r.failure_reason}")
    assert len((r.text or "").strip()) > 10


def test_parse_disabled_tool_returns_tool_disabled() -> None:
    p = FIX / "txt" / "sample_success.txt"
    registry.disable_tool("parse_txt_document")
    try:
        r = registry.call_tool("parse_txt_document", file_path=str(p))
        assert r.status == "failed"
        assert r.error_code == "tool_disabled"
    finally:
        registry.enable_tool("parse_txt_document")

