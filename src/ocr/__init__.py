"""
OCR helpers for the Mitchopolis Evidence Engine.

Exports:
- safe_extract_text(): best-effort text extraction for PDFs/images/text files.

PDF behavior:
- Try embedded text first (PyMuPDF).
- If a page has little/no embedded text, fall back to OCR (pytesseract) for that page.
This provides a "scanned-PDF fallback" without requiring extra libraries.
"""

from dataclasses import dataclass
from typing import Optional, Union, List
from pathlib import Path
from xml.etree import ElementTree
import io
import zipfile


@dataclass(frozen=True)
class ExtractionWarning:
    code: str
    message: str


@dataclass(frozen=True)
class TextExtractionResult:
    text: str
    method: str
    warnings: tuple[ExtractionWarning, ...] = ()


def _add_warning(
    warnings: List[ExtractionWarning], code: str, message: str
) -> None:
    if any(warning.code == code for warning in warnings):
        return
    warnings.append(ExtractionWarning(code=code, message=message))


def _completed_result(
    text: str,
    method: str,
    warnings: List[ExtractionWarning],
) -> TextExtractionResult:
    cleaned_text = (text or "").strip()
    if cleaned_text and "ocr" in method:
        _add_warning(
            warnings,
            "ocr_review_required",
            "OCR-derived text may contain recognition errors; verify it "
            "against the source file.",
        )
    elif not cleaned_text:
        _add_warning(
            warnings,
            "no_text_extracted",
            "No usable text was extracted from the media file.",
        )
    return TextExtractionResult(
        text=cleaned_text,
        method=method,
        warnings=tuple(warnings),
    )


def _extract_text_with_diagnostics(
    media_path: Optional[Union[str, Path]],
    *,
    max_pdf_pages: int = 25,
    ocr_dpi: int = 200,
    enable_pdf_ocr: bool = True,
) -> TextExtractionResult:
    """
    Best-effort extraction with stable, non-sensitive warning codes.

    Supported:
    - .txt/.md/.log -> read text
    - .docx -> read Word document XML text
    - images -> OCR via pytesseract
    - .pdf -> embedded text; OCR fallback for scanned pages
    """
    warnings: List[ExtractionWarning] = []

    if not media_path:
        _add_warning(
            warnings,
            "media_path_missing",
            "No media path was provided.",
        )
        return TextExtractionResult(text="", method="none", warnings=tuple(warnings))

    try:
        p = Path(media_path).expanduser()
    except Exception:
        _add_warning(
            warnings,
            "media_path_invalid",
            "The media path could not be interpreted.",
        )
        return TextExtractionResult(text="", method="none", warnings=tuple(warnings))

    if not p.is_absolute():
        p = (Path.cwd() / p).resolve()

    if not p.exists():
        _add_warning(
            warnings,
            "media_not_found",
            "The media file was not found.",
        )
        return TextExtractionResult(text="", method="none", warnings=tuple(warnings))
    if not p.is_file():
        _add_warning(
            warnings,
            "media_not_file",
            "The media path does not identify a regular file.",
        )
        return TextExtractionResult(text="", method="none", warnings=tuple(warnings))

    ext = p.suffix.lower()

    # Plain text
    if ext in {".txt", ".md", ".log"}:
        try:
            extracted = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            extracted = ""
            _add_warning(
                warnings,
                "text_read_failed",
                "The text file could not be read.",
            )
        return _completed_result(extracted, "plain_text", warnings)

    if ext == ".docx":
        try:
            with zipfile.ZipFile(p) as docx:
                xml = docx.read("word/document.xml")
            root = ElementTree.fromstring(xml)
            namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
            parts = [
                node.text
                for node in root.iter(f"{namespace}t")
                if node.text
            ]
            extracted = "\n".join(parts)
        except Exception:
            extracted = ""
            _add_warning(
                warnings,
                "docx_read_failed",
                "The Word document could not be read.",
            )
        return _completed_result(extracted, "docx_text", warnings)

    # Images -> OCR
    if ext in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}:
        try:
            from PIL import Image
            import pytesseract
        except Exception:
            _add_warning(
                warnings,
                "image_ocr_unavailable",
                "Image OCR dependencies are unavailable.",
            )
            return _completed_result("", "image_ocr", warnings)

        try:
            with Image.open(str(p)) as img:
                extracted = pytesseract.image_to_string(img) or ""
        except Exception:
            extracted = ""
            _add_warning(
                warnings,
                "image_ocr_failed",
                "Image OCR did not complete successfully.",
            )
        return _completed_result(extracted, "image_ocr", warnings)

    # PDFs -> embedded text with scanned-page OCR fallback
    if ext == ".pdf":
        try:
            import fitz  # PyMuPDF
        except Exception:
            _add_warning(
                warnings,
                "pdf_reader_unavailable",
                "The PDF text extraction dependency is unavailable.",
            )
            return _completed_result("", "pdf", warnings)

        try:
            doc = fitz.open(str(p))
        except Exception:
            _add_warning(
                warnings,
                "pdf_open_failed",
                "The PDF could not be opened for text extraction.",
            )
            return _completed_result("", "pdf", warnings)

        out_chunks: List[str] = []
        used_embedded_text = False
        used_ocr = False

        # Lazy-load OCR libs only if needed
        ocr_ready = False
        Image = None
        pytesseract = None

        def _ensure_ocr() -> bool:
            nonlocal ocr_ready, Image, pytesseract
            if ocr_ready:
                return True
            try:
                from PIL import Image as _Image
                import pytesseract as _pytesseract

                _pytesseract.get_tesseract_version()

                Image = _Image
                pytesseract = _pytesseract
                ocr_ready = True
                return True
            except Exception:
                return False

        try:
            page_count = doc.page_count
            limit = min(
                page_count,
                max_pdf_pages if max_pdf_pages and max_pdf_pages > 0 else page_count,
            )
            if limit < page_count:
                _add_warning(
                    warnings,
                    "pdf_page_limit",
                    f"Only the first {limit} of {page_count} PDF pages were inspected.",
                )

            scale = float(ocr_dpi) / 72.0 if ocr_dpi and ocr_dpi > 0 else 200.0 / 72.0
            matrix = fitz.Matrix(scale, scale)

            for i in range(limit):
                page = doc.load_page(i)

                # 1) Try embedded text first
                try:
                    txt = (page.get_text("text") or "").strip()
                except Exception:
                    txt = ""
                    _add_warning(
                        warnings,
                        "pdf_text_failed",
                        f"Embedded text could not be read from PDF page {i + 1}.",
                    )
                if len(txt) >= 40:
                    out_chunks.append(txt)
                    used_embedded_text = True
                    continue

                # 2) Scanned fallback (OCR)
                if not enable_pdf_ocr:
                    _add_warning(
                        warnings,
                        "pdf_ocr_disabled",
                        "One or more PDF pages had too little embedded text "
                        "and PDF OCR was disabled.",
                    )
                    if txt:
                        out_chunks.append(txt)
                        used_embedded_text = True
                    continue

                if not _ensure_ocr():
                    _add_warning(
                        warnings,
                        "pdf_ocr_unavailable",
                        "PDF OCR dependencies or the Tesseract runtime are unavailable.",
                    )
                    if txt:
                        out_chunks.append(txt)
                        used_embedded_text = True
                    continue

                try:
                    pix = page.get_pixmap(matrix=matrix, alpha=False)
                    img = Image.open(io.BytesIO(pix.tobytes("png")))
                    ocr_txt = (pytesseract.image_to_string(img) or "").strip()

                    if ocr_txt:
                        out_chunks.append(ocr_txt)
                        used_ocr = True
                    elif txt:
                        out_chunks.append(txt)
                        used_embedded_text = True
                    else:
                        _add_warning(
                            warnings,
                            "pdf_page_no_text",
                            f"No usable text was extracted from PDF page {i + 1}.",
                        )
                except Exception:
                    _add_warning(
                        warnings,
                        "pdf_ocr_failed",
                        f"OCR did not complete successfully for PDF page {i + 1}.",
                    )
                    if txt:
                        out_chunks.append(txt)
                        used_embedded_text = True

        finally:
            try:
                doc.close()
            except Exception:
                pass

        if used_embedded_text and used_ocr:
            method = "pdf_text_and_ocr"
        elif used_ocr:
            method = "pdf_ocr"
        elif used_embedded_text:
            method = "pdf_text"
        else:
            method = "pdf"
        return _completed_result("\n\n".join(out_chunks), method, warnings)

    # Unknown type
    shown_extension = ext or "[none]"
    _add_warning(
        warnings,
        "unsupported_media_type",
        f"Media type '{shown_extension}' is not supported.",
    )
    return TextExtractionResult(text="", method="unsupported", warnings=tuple(warnings))


def extract_text_with_diagnostics(
    media_path: Optional[Union[str, Path]],
    *,
    max_pdf_pages: int = 25,
    ocr_dpi: int = 200,
    enable_pdf_ocr: bool = True,
) -> TextExtractionResult:
    """Return extraction text and diagnostics without surfacing exceptions."""
    try:
        return _extract_text_with_diagnostics(
            media_path,
            max_pdf_pages=max_pdf_pages,
            ocr_dpi=ocr_dpi,
            enable_pdf_ocr=enable_pdf_ocr,
        )
    except Exception:
        return TextExtractionResult(
            text="",
            method="none",
            warnings=(
                ExtractionWarning(
                    code="extraction_failed",
                    message="Text extraction did not complete successfully.",
                ),
            ),
        )


def safe_extract_text(
    media_path: Optional[Union[str, Path]],
    *,
    max_pdf_pages: int = 25,
    ocr_dpi: int = 200,
    enable_pdf_ocr: bool = True,
) -> str:
    """Compatibility wrapper that returns extracted text and never raises."""
    return extract_text_with_diagnostics(
        media_path,
        max_pdf_pages=max_pdf_pages,
        ocr_dpi=ocr_dpi,
        enable_pdf_ocr=enable_pdf_ocr,
    ).text


__all__ = [
    "ExtractionWarning",
    "TextExtractionResult",
    "extract_text_with_diagnostics",
    "safe_extract_text",
]
