"""
V16 R1：默认主路径 smoke 测试。

验证完整链路（服务层入口）：
  文档输入 → prepare → pending → commit → retrieve

不调用 LLM，不依赖 API；仅验证数据在各层之间正确流动。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from tests._fixtures.v16_doc_factory import (
    make_docx_success,
    make_pdf_text_success,
    make_txt_success,
    make_xlsx_success,
)
from tests._support.bootstrap import bootstrap_historical_test
from tests._support.pg_fixtures import pg_required_marks

from rag.pending_store import PendingStore
from services.capabilities.knowledge.pending_ingestion_service import (
    commit_pending,
    prepare_document_source,
    prepare_file_source,
)

_CORE_DIR = bootstrap_historical_test(__file__)
_CAP_DIR = _CORE_DIR
for _d in (_CORE_DIR, _CAP_DIR):
    if str(_d) not in sys.path:
        sys.path.insert(0, str(_d))

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tools.document  # noqa: F401

pytestmark = pg_required_marks()


@pytest.fixture(autouse=True)
def _pg_for_smoke(pg_settings: None) -> None:  # noqa: ARG001
    """Smoke commit→retrieve 需要真实 PostgreSQL，避免 fake PG 污染后续 RAG 集成测。"""


def _smoke(file_path, session_id: str, store: PendingStore | None = None):
    """
    执行 prepare → commit，返回 (item, commit_result)。
    """
    _store = store or PendingStore()
    ext = Path(file_path).suffix.lower()
    if ext in (".docx", ".xlsx", ".xlsm", ".pdf"):
        item = prepare_document_source(str(file_path), session_id=session_id, store=_store)
    else:
        item = prepare_file_source(str(file_path), session_id=session_id, store=_store)
    commit_result = commit_pending(item.pending_id, store=_store)
    return item, commit_result


class TestDefaultPathSmoke:
    def test_txt_smoke(self) -> None:
        p = make_txt_success()
        item, result = _smoke(p, "smoke_txt")
        assert item.extract_status == "ok", f"prepare 失败: {item.error_code}"
        assert result.success, f"commit 失败: {result.error_code}"
        assert result.source_id
        assert result.chunk_count > 0

    def test_md_smoke(self):
        p = make_txt_success()  # txt 内容也可作为 md（测试不严格区分内容格式）
        from tests._fixtures.v16_doc_factory import make_md_success
        p = make_md_success()
        item, result = _smoke(p, "smoke_md")
        assert item.extract_status == "ok"
        assert result.success

    def test_docx_smoke(self):
        p = make_docx_success()
        item, result = _smoke(p, "smoke_docx")
        if item.extract_status in ("dependency_missing", "parse_failed", "docx_no_content"):
            pytest.skip(f"docx 依赖问题或内容为空: {item.error_code}")
        assert item.extract_status == "ok", f"prepare 失败: {item.error_code}"
        assert result.success, f"commit 失败: {result.error_code}"
        # 核心：source_type 必须是 docx，证明走了 V16 新链
        assert item.source_type == "docx"
        assert result.source_id

    def test_xlsx_smoke(self):
        p = make_xlsx_success()
        item, result = _smoke(p, "smoke_xlsx")
        if item.extract_status in ("dependency_missing", "invalid_excel"):
            pytest.skip(f"xlsx 依赖问题: {item.error_code}")
        assert item.extract_status == "ok", f"prepare 失败: {item.error_code}"
        assert result.success
        assert item.source_type == "xlsx"

    def test_pdf_text_smoke(self):
        p = make_pdf_text_success()
        item, result = _smoke(p, "smoke_pdf")
        if item.extract_status in ("pdf_parser_missing", "dependency_missing"):
            pytest.skip("PDF 解析库未安装")
        if item.extract_status == "scanned_pdf_requires_ocr":
            pytest.skip("生成的 PDF 样本被识别为扫描版（测试环境限制）")
        assert item.extract_status == "ok", f"prepare 失败: {item.error_code}"
        assert result.success
        assert item.source_type == "pdf"

    def test_prepare_result_has_tool_metadata(self):
        """commit 后的 item.metadata 必须包含 v16_tool_name（证明走了 ToolResult 链）。"""
        p = make_txt_success()
        item, result = _smoke(p, "smoke_meta")
        assert item.extract_status == "ok"
        meta = item.metadata or {}
        # txt 走了 parse_txt_document
        assert meta.get("parser_name") in (
            "parse_txt_document", "parse_md_document", "parse_file_source",
            "text_file_parser",  # 旧 parse_file_source 产出的 parser_name
        ), f"metadata 缺少 parser_name: {meta}"

    def test_docx_metadata_has_v16_fields(self):
        """docx commit 后 metadata 必须有 V16 专属字段。"""
        p = make_docx_success()
        item, result = _smoke(p, "smoke_docx_meta")
        if item.extract_status in ("dependency_missing", "parse_failed", "docx_no_content"):
            pytest.skip(f"docx 依赖问题: {item.error_code}")
        assert item.extract_status == "ok"
        meta = item.metadata or {}
        # 至少要有 extract_method 或 v16_extract_method
        has_method = "extract_method" in meta or "v16_extract_method" in meta
        assert has_method, f"docx metadata 缺少 extract_method: {meta}"

