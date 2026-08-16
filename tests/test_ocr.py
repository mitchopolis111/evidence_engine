import logging

import fitz
import pytesseract

from src.ocr import safe_extract_text


def test_safe_extract_text_accepts_path_object(tmp_path):
    text_file = tmp_path / "example.txt"
    text_file.write_text("Path objects work", encoding="utf-8")

    assert safe_extract_text(text_file) == "Path objects work"


def test_missing_tesseract_is_nonfatal_and_logged(tmp_path, monkeypatch, caplog):
    pdf_path = tmp_path / "scanned.pdf"
    with fitz.open() as document:
        document.new_page()
        document.save(pdf_path)

    def unavailable():
        raise RuntimeError("tesseract executable was not found")

    monkeypatch.setenv("EE_SCANNED_PDF_OCR", "1")
    monkeypatch.setattr(pytesseract, "get_tesseract_version", unavailable)

    with caplog.at_level(logging.WARNING, logger="src.ocr"):
        assert safe_extract_text(pdf_path) == ""

    assert "Tesseract is unavailable" in caplog.text
    assert "scanned PDF OCR skipped" in caplog.text
