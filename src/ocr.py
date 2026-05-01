import os
from pathlib import Path


def _truthy_env(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default


def safe_extract_text(path: str) -> str:
    """
    Extract text from:
    - .txt (read)
    - images (pytesseract)
    - .pdf (PyMuPDF embedded text; scanned fallback OCR if enabled)
    """
    if not path:
        return ""

    p = Path(path).expanduser()
    if not p.is_absolute():
        # optional: if you want relative paths to be treated as INBOX-relative
        inbox = os.getenv("INBOX")
        if inbox:
            p2 = Path(inbox) / p
            if p2.exists():
                p = p2

    if not p.exists():
        return ""

    ext = p.suffix.lower()

    # ---- TEXT FILES ----
    if ext in {".txt", ".log"}:
        try:
            return p.read_text(encoding="utf-8", errors="ignore").strip()
        except Exception:
            return ""

    # ---- PDFS ----
    if ext == ".pdf":
        extracted = ""
        try:
            import fitz  # PyMuPDF
            with fitz.open(p) as doc:
                parts = [(page.get_text("text") or "") for page in doc]
            extracted = "\n".join(parts).strip()
        except Exception:
            extracted = ""

        min_chars = _env_int("EE_PDF_TEXT_MIN_CHARS", 40)
        if extracted and len(extracted) >= min_chars:
            return extracted

        # scanned fallback disabled -> return whatever embedded text we found (maybe empty)
        if not _truthy_env("EE_SCANNED_PDF_OCR", "0"):
            return extracted

        # scanned fallback OCR
        try:
            import fitz
            from PIL import Image
            import pytesseract

            # If tesseract binary isn't available, don't crash
            try:
                pytesseract.get_tesseract_version()
            except Exception:
                return extracted

            max_pages = _env_int("EE_SCANNED_PDF_MAX_PAGES", 3)
            dpi = _env_int("EE_SCANNED_PDF_DPI", 200)
            zoom = max(dpi, 72) / 72.0

            out_parts: list[str] = []
            with fitz.open(p) as doc:
                n = min(doc.page_count, max_pages)
                for i in range(n):
                    page = doc.load_page(i)
                    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)

                    mode = "RGB"
                    img = Image.frombytes(mode, [pix.width, pix.height], pix.samples)

                    txt = (pytesseract.image_to_string(img) or "").strip()
                    if txt:
                        out_parts.append(txt)

            scanned = "\n\n".join(out_parts).strip()
            combined = "\n".join([extracted.strip(), scanned.strip()]).strip()
            return combined
        except Exception:
            return extracted

    # ---- IMAGES ----
    if ext in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}:
        try:
            from PIL import Image
            import pytesseract
            img = Image.open(p)
            return (pytesseract.image_to_string(img) or "").strip()
        except Exception:
            return ""

    return ""
