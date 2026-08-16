import logging
import os
from pathlib import Path
from typing import Optional, Union


logger = logging.getLogger(__name__)

PathInput = Union[str, os.PathLike[str]]
SUPPORTED_TEXT_EXTENSIONS = frozenset({".txt", ".log"})
SUPPORTED_IMAGE_EXTENSIONS = frozenset(
    {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}
)


def _truthy_env(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default


def _resolve_media_path(path: PathInput) -> Optional[Path]:
    """Resolve user and optional INBOX-relative paths without raising."""
    try:
        resolved = Path(path).expanduser()
    except (TypeError, ValueError, OSError) as exc:
        logger.warning("Unable to resolve OCR input path %r: %s", path, exc)
        return None

    if not resolved.is_absolute():
        inbox = os.getenv("INBOX")
        if inbox:
            candidate = Path(inbox).expanduser() / resolved
            if candidate.exists():
                resolved = candidate

    return resolved


def safe_extract_text(path: PathInput) -> str:
    """
    Extract text from:
    - .txt (read)
    - images (pytesseract)
    - .pdf (PyMuPDF embedded text; scanned fallback OCR if enabled)
    """
    if not path:
        return ""

    p = _resolve_media_path(path)
    if p is None:
        return ""

    if not p.exists():
        return ""

    ext = p.suffix.lower()

    # ---- TEXT FILES ----
    if ext in SUPPORTED_TEXT_EXTENSIONS:
        try:
            return p.read_text(encoding="utf-8", errors="ignore").strip()
        except Exception as exc:
            logger.warning("Text extraction failed for %s: %s", p, exc)
            return ""

    # ---- PDFS ----
    if ext == ".pdf":
        extracted = ""
        try:
            import fitz  # PyMuPDF
            with fitz.open(p) as doc:
                parts = [(page.get_text("text") or "") for page in doc]
            extracted = "\n".join(parts).strip()
        except Exception as exc:
            logger.warning("Embedded PDF text extraction failed for %s: %s", p, exc)
            extracted = ""

        min_chars = max(0, _env_int("EE_PDF_TEXT_MIN_CHARS", 40))
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
            except Exception as exc:
                logger.warning(
                    "Tesseract is unavailable; scanned PDF OCR skipped for %s: %s",
                    p,
                    exc,
                )
                return extracted

            max_pages = max(0, _env_int("EE_SCANNED_PDF_MAX_PAGES", 3))
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
        except Exception as exc:
            logger.warning("Scanned PDF OCR failed for %s: %s", p, exc)
            return extracted

    # ---- IMAGES ----
    if ext in SUPPORTED_IMAGE_EXTENSIONS:
        try:
            from PIL import Image
            import pytesseract

            try:
                pytesseract.get_tesseract_version()
            except Exception as exc:
                logger.warning(
                    "Tesseract is unavailable; image OCR skipped for %s: %s",
                    p,
                    exc,
                )
                return ""

            with Image.open(p) as img:
                return (pytesseract.image_to_string(img) or "").strip()
        except Exception as exc:
            logger.warning("Image OCR failed for %s: %s", p, exc)
            return ""

    return ""
