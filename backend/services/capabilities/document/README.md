# Document Capability Plane

Unified orchestration for document parse / OCR / summarize / early prepare.

Application fast path and MiddleAgent complex gather must import from this package — not `tools.document.*` or `tools.ocr.*` directly at orchestration layers.

| Module | Role |
|---|---|
| `parse_service.py` | quick parse via document tool registry |
| `ocr_service.py` | sync OCR + `document_ocr` async enqueue |
| `summarize_service.py` | document fast lane 首答摘要 |
| `early_document_support.py` | complex gather 文档 prepare 编排 |
| `async_document_pipeline.py` | async worker 执行 document OCR |
| `types.py` | shared outcome types |
