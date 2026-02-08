"""
OCR helpers for the Mitchopolis Evidence Engine.

Exports:
- safe_extract_text(): best-effort text extraction for PDFs/images/text files.

PDF behavior:
- Try embedded text first (PyMuPDF).
- If a page has little/no embedded text, fall back to OCR (pytesseract) for that page.
This provides a "scanned-PDF fallback" without requiring extra libraries.
"""

from typing import Optional, Union, List
from pathlib import Path
import io


def safe_extract_text(
    media_path: Optional[Union[str, Path]],
    *,
    max_pdf_pages: int = 25,
    ocr_dpi: int = 200,
) -> str:
    """
    Best-effort extraction. Never raises: returns "" on failure.

    Supported:
    - .txt/.md/.log -> read text
    - images -> OCR via pytesseract
    - .pdf -> embedded text; OCR fallback for scanned pages
    """
    if not media_path:
        return ""

    try:
        p = Path(media_path).expanduser()
    except Exception:
        return ""

    if not p.is_absolute():
        p = (Path.cwd() / p).resolve()

    if not p.exists() or not p.is_file():
        return ""

    ext = p.suffix.lower()

    # Plain text
    if ext in {".txt", ".md", ".log"}:
        try:
            return p.read_text(encoding="utf-8", errors="ignore").strip()
        except Exception:
            return ""

    # Images -> OCR
    if ext in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}:
        try:
            from PIL import Image
            import pytesseract

            img = Image.open(str(p))
            return (pytesseract.image_to_string(img) or "").strip()
        except Exception:
            return ""

    # PDFs -> embedded text with scanned-page OCR fallback
    if ext == ".pdf":
        try:
            import fitz  # PyMuPDF
        except Exception:
            return ""

        try:
            doc = fitz.open(str(p))
        except Exception:
            return ""

        out_chunks: List[str] = []

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

            scale = float(ocr_dpi) / 72.0 if ocr_dpi and ocr_dpi > 0 else 200.0 / 72.0
            matrix = fitz.Matrix(scale, scale)

            for i in range(limit):
                page = doc.load_page(i)

                # 1) Try embedded text first
                txt = (page.get_text("text") or "").strip()
                if len(txt) >= 40:
                    out_chunks.append(txt)
                    continue

                # 2) Scanned fallback (OCR)
                if not _ensure_ocr():
                    # Can't OCR; keep any partial embedded text
                    if txt:
                        out_chunks.append(txt)
                    continue

                try:
                    pix = page.get_pixmap(matrix=matrix, alpha=False)
                    img = Image.open(io.BytesIO(pix.tobytes("png")))
                    ocr_txt = (pytesseract.image_to_string(img) or "").strip()

                    if ocr_txt:
                        out_chunks.append(ocr_txt)
                    elif txt:
                        out_chunks.append(txt)
                except Exception:
                    if txt:
                        out_chunks.append(txt)

        finally:
            try:
                doc.close()
            except Exception:
                pass

        return "\n\n".join([c for c in out_chunks if c]).strip()

    # Unknown type
    return ""


__all__ = ["safe_extract_text"]