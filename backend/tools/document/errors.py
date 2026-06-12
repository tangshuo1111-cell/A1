"""
文档工具统一错误码常量。

所有 DocumentToolResult.error_code 必须来自此文件定义的常量，
不允许在工具内散写字符串错误码。
"""

# ── 通用依赖/格式错误 ──────────────────────────────────────────────────────
DEPENDENCY_MISSING = "dependency_missing"
PARSER_DEPENDENCY_MISSING = "parser_dependency_missing"
UNSUPPORTED_FILE_TYPE = "unsupported_file_type"
FILE_NOT_FOUND = "file_not_found"
FILE_TOO_LARGE = "file_too_large"
PARSE_FAILED = "parse_failed"

# ── 内容质量错误 ──────────────────────────────────────────────────────────
EMPTY_EXTRACTED_TEXT = "empty_extracted_text"
INVALID_TEXT_QUALITY = "invalid_text_quality"
LOW_CONTENT_QUALITY = "low_content_quality"

# ── PDF 专属 ──────────────────────────────────────────────────────────────
SCANNED_PDF_REQUIRES_OCR = "scanned_pdf_requires_ocr"
PDF_TOO_MANY_PAGES = "pdf_too_many_pages"
PDF_ENCRYPTED = "pdf_encrypted"
PDF_PARSER_MISSING = "pdf_parser_missing"

# ── Excel 专属 ────────────────────────────────────────────────────────────
INVALID_EXCEL = "invalid_excel"
EMPTY_SHEET = "empty_sheet"
EXCEL_TOO_LARGE = "excel_too_large"

# ── Word 专属 ─────────────────────────────────────────────────────────────
DOCX_NO_CONTENT = "docx_no_content"

# ── 生命周期错误 ──────────────────────────────────────────────────────────
COMMIT_FAILED = "commit_failed"
RETRIEVE_NO_MATCH = "retrieve_no_match"

# ── 工具禁用/限制 ─────────────────────────────────────────────────────────
TOOL_DISABLED = "tool_disabled"
TOOL_NOT_FOUND = "tool_not_found"
