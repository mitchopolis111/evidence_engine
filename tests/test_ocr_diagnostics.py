from src import ocr
from src.ocr import extract_text_with_diagnostics, safe_extract_text


def test_text_extraction_diagnostics_preserve_safe_wrapper(tmp_path):
    source = tmp_path / "evidence.txt"
    source.write_text("Source-linked evidence", encoding="utf-8")

    result = extract_text_with_diagnostics(source)

    assert result.text == "Source-linked evidence"
    assert result.method == "plain_text"
    assert result.warnings == ()
    assert safe_extract_text(source) == result.text


def test_text_extraction_diagnostics_report_missing_file(tmp_path):
    result = extract_text_with_diagnostics(tmp_path / "missing.pdf")

    assert result.text == ""
    assert result.method == "none"
    assert [warning.code for warning in result.warnings] == ["media_not_found"]


def test_text_extraction_diagnostics_report_unsupported_type(tmp_path):
    source = tmp_path / "evidence.bin"
    source.write_bytes(b"unsupported")

    result = extract_text_with_diagnostics(source)

    assert result.text == ""
    assert result.method == "unsupported"
    assert [warning.code for warning in result.warnings] == [
        "unsupported_media_type"
    ]


def test_text_extraction_diagnostics_report_blank_supported_file(tmp_path):
    source = tmp_path / "blank.txt"
    source.write_text("", encoding="utf-8")

    result = extract_text_with_diagnostics(source)

    assert result.text == ""
    assert result.method == "plain_text"
    assert [warning.code for warning in result.warnings] == ["no_text_extracted"]


def test_completed_ocr_result_requires_source_review():
    result = ocr._completed_result("recognized text", "pdf_ocr", [])

    assert [warning.code for warning in result.warnings] == [
        "ocr_review_required"
    ]


def test_detailed_extraction_never_surfaces_internal_exception(monkeypatch):
    def fail_extraction(*args, **kwargs):
        raise RuntimeError("sensitive internal failure")

    monkeypatch.setattr(ocr, "_extract_text_with_diagnostics", fail_extraction)

    result = extract_text_with_diagnostics("evidence.pdf")

    assert result.text == ""
    assert [warning.code for warning in result.warnings] == ["extraction_failed"]
    assert safe_extract_text("evidence.pdf") == ""
