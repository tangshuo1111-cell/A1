from __future__ import annotations

from pathlib import Path

import pytest

from tools.document.tool_result import DocumentToolResult
from tools.ocr import errors as ocr_errors
from tools.ocr.providers import OcrProviderOutcome


@pytest.fixture
def ocr_mod():
    from tools.ocr import ocr_document as mod

    return mod


def _stub_task_runtime(monkeypatch: pytest.MonkeyPatch, mod) -> None:
    monkeypatch.setattr(mod, "create_task_record", lambda **_kwargs: "ocr-task-1")
    monkeypatch.setattr(mod.task_job_store, "mark_task_running", lambda *a, **k: None)
    monkeypatch.setattr(mod.task_job_store, "mark_task_failed", lambda *a, **k: None)
    monkeypatch.setattr(mod.task_job_store, "mark_task_succeeded", lambda *a, **k: None)


def test_tencent_ocr_falls_back_to_local_tesseract_for_image(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    ocr_mod,
) -> None:
    _stub_task_runtime(monkeypatch, ocr_mod)
    img = tmp_path / "scan.png"
    img.write_bytes(b"fake-image")

    monkeypatch.setattr(ocr_mod.settings, "v16_enable_ocr", True)
    monkeypatch.setattr(ocr_mod.settings, "v16_ocr_provider", "tencent")
    monkeypatch.setattr(ocr_mod.settings, "v16_enable_external_processing", True)
    monkeypatch.setattr(ocr_mod.settings, "v16_enable_paid_ocr", True)
    monkeypatch.setattr(ocr_mod.settings, "v16_tencent_secret_id", "sid")
    monkeypatch.setattr(ocr_mod.settings, "v16_tencent_secret_key", "skey")
    monkeypatch.setattr(
        ocr_mod,
        "run_tencent_ocr",
        lambda *a, **k: OcrProviderOutcome(
            ok=False,
            error_code=ocr_errors.OCR_PROVIDER_ERROR,
            failure_reason="tencent timeout",
            provider_type="tencent",
            production_ready=True,
            external_processing=True,
            duration_ms=12.0,
        ),
    )
    monkeypatch.setattr(
        ocr_mod,
        "run_local_tesseract",
        lambda path: OcrProviderOutcome(
            ok=True,
            text="local ocr text",
            pages=[{"page": 1, "text": "local ocr text"}],
            provider_type="local_tesseract",
            production_ready=True,
            external_processing=False,
            duration_ms=8.0,
        ),
    )

    result: DocumentToolResult = ocr_mod._ocr_document(str(img))

    assert result.status == "success"
    assert result.text == "local ocr text"
    assert result.metadata["provider"] == "tencent"
    assert result.metadata["primary_provider"] == "tencent"
    assert result.metadata["fallback_provider"] == "local_tesseract"
    assert result.metadata["fallback_used"] is True
    assert result.metadata["quality_degraded"] is True
    assert result.warnings == ["primary_ocr_failed:ocr_provider_error -> local_tesseract"]
    assert "fallback=local_tesseract" in result.trace[0]


def test_tencent_ocr_does_not_fallback_for_pdf(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    ocr_mod,
) -> None:
    _stub_task_runtime(monkeypatch, ocr_mod)
    pdf = tmp_path / "scan.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    monkeypatch.setattr(ocr_mod.settings, "v16_enable_ocr", True)
    monkeypatch.setattr(ocr_mod.settings, "v16_ocr_provider", "tencent")
    monkeypatch.setattr(ocr_mod.settings, "v16_enable_external_processing", True)
    monkeypatch.setattr(ocr_mod.settings, "v16_enable_paid_ocr", True)
    monkeypatch.setattr(ocr_mod.settings, "v16_tencent_secret_id", "sid")
    monkeypatch.setattr(ocr_mod.settings, "v16_tencent_secret_key", "skey")
    monkeypatch.setattr(ocr_mod, "_pdf_page_count", lambda _path: 1)
    monkeypatch.setattr(
        ocr_mod,
        "run_tencent_ocr",
        lambda *a, **k: OcrProviderOutcome(
            ok=False,
            error_code=ocr_errors.OCR_PROVIDER_ERROR,
            failure_reason="tencent timeout",
            provider_type="tencent",
            production_ready=True,
            external_processing=True,
            duration_ms=12.0,
        ),
    )

    seen = {"called": False}

    def _never_called(_path: Path) -> OcrProviderOutcome:
        seen["called"] = True
        return OcrProviderOutcome(ok=True, text="should not happen")

    monkeypatch.setattr(ocr_mod, "run_local_tesseract", _never_called)

    result: DocumentToolResult = ocr_mod._ocr_document(str(pdf))

    assert result.status == "failed"
    assert result.error_code == ocr_errors.OCR_PROVIDER_ERROR
    assert seen["called"] is False


def test_tencent_ocr_config_error_does_not_trigger_local_fallback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    ocr_mod,
) -> None:
    _stub_task_runtime(monkeypatch, ocr_mod)
    img = tmp_path / "scan.png"
    img.write_bytes(b"fake-image")

    monkeypatch.setattr(ocr_mod.settings, "v16_enable_ocr", True)
    monkeypatch.setattr(ocr_mod.settings, "v16_ocr_provider", "tencent")
    monkeypatch.setattr(ocr_mod.settings, "v16_enable_external_processing", True)
    monkeypatch.setattr(ocr_mod.settings, "v16_enable_paid_ocr", True)
    monkeypatch.setattr(
        ocr_mod,
        "run_tencent_ocr",
        lambda *a, **k: OcrProviderOutcome(
            ok=False,
            error_code=ocr_errors.OCR_NOT_CONFIGURED,
            failure_reason="missing secret",
            provider_type="tencent",
            production_ready=True,
            external_processing=True,
            duration_ms=5.0,
        ),
    )

    seen = {"called": False}

    def _never_called(_path: Path) -> OcrProviderOutcome:
        seen["called"] = True
        return OcrProviderOutcome(ok=True, text="should not happen")

    monkeypatch.setattr(ocr_mod, "run_local_tesseract", _never_called)

    result: DocumentToolResult = ocr_mod._ocr_document(str(img))

    assert result.status == "failed"
    assert result.error_code == ocr_errors.OCR_NOT_CONFIGURED
    assert seen["called"] is False
