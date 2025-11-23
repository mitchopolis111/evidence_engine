import pytesseract
from PIL import Image
import fitz  # PyMuPDF
import os

def extract_text(file_path: str) -> str:
    if file_path.lower().endswith(".pdf"):
        return extract_pdf(file_path)
    else:
        return extract_image(file_path)

def extract_image(file_path: str) -> str:
    img = Image.open(file_path)
    return pytesseract.image_to_string(img)

def extract_pdf(file_path: str) -> str:
    text = ""
    doc = fitz.open(file_path)
    for page in doc:
        text += page.get_text()
    return text


def safe_extract_text(file_path: str) -> str:
    """
    Safe OCR wrapper that avoids throwing and returns an empty string on failure.
    """
    if not file_path or not isinstance(file_path, str):
        return ""

    if not os.path.exists(file_path):
        return ""

    try:
        return extract_text(file_path)
    except Exception:
        return ""
