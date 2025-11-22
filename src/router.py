from fastapi import APIRouter, UploadFile
from .ocr import extract_text
from .classifier import classify_text
from .timeline import build_timeline_item
from .db import db

router = APIRouter()

@router.post("/process")
async def process_evidence(file: UploadFile):
    file_path = f"/tmp/{file.filename}"
    with open(file_path, "wb") as f:
        f.write(await file.read())

    text = extract_text(file_path)
    classification = classify_text(text)
    timeline_item = build_timeline_item(text, classification)

    db.processed.insert_one({
        "filename": file.filename,
        "classification": classification,
        "timeline": timeline_item,
        "full_text": text
    })

    return {
        "status": "processed",
        "classification": classification,
        "timeline_item": timeline_item
    }
