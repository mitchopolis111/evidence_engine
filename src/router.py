from pathlib import Path
import os
from fastapi.responses import FileResponse
from .utils.zip_exporter import generate_evidence_zip
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional
import uuid
import logging
from .classifier import classify_text
from .ocr import safe_extract_text
from .timeline import extract_date
from .db import get_collection
from datetime import datetime
from pymongo import UpdateOne

router = APIRouter()

logger = logging.getLogger(__name__)

# In-memory timeline cache keyed by case_id (dev-only fallback).
CASE_TIMELINES: dict[str, List["TimelineEntry"]] = {}


def _persist_timeline_entries(case_id: str, entries: List["TimelineEntry"]):
    """
    Persist timeline entries to MongoDB if configured. Falls back to memory when
    Mongo is not available.
    """
    col = get_collection("timelines")
    if col is None:
        CASE_TIMELINES[case_id] = entries
        return

    ops = []
    for entry in entries:
        doc = {
            "id": entry.id,
            "case_id": entry.case_id,
            "summary": entry.summary,
            "timestamp": entry.timestamp,
            "evidence_ids": entry.evidence_ids,
            "predicted_type": entry.predicted_type,
            "ocr_used": entry.ocr_used,
        }
        ops.append(
            UpdateOne(
                {"id": entry.id},
                {"$set": doc, "$setOnInsert": {"created_at": datetime.utcnow()}},
                upsert=True,
            )
        )

    try:
        if ops:
            col.bulk_write(ops, ordered=False)
    except Exception:
        logger.exception("Failed to persist timeline entries to MongoDB")
        raise HTTPException(status_code=500, detail="Failed to persist timeline")


class EvidenceItem(BaseModel):
    id: Optional[str] = Field(
        default=None,
        description="Optional client-side id for the evidence item",
    )
    source: str = Field(
        ...,
        description="Where this evidence came from (e.g. 'ofw', 'sms', 'photo')",
    )
    content: str = Field(
        ...,
        description="Raw text or description associated with the evidence",
    )
    media_path: Optional[str] = Field(
        default=None,
        description="Absolute or relative path to the underlying file, if any",
    )
    tags: List[str] = Field(
        default_factory=list,
        description="Optional tags applied by the client",
    )


class ProcessEvidenceRequest(BaseModel):
    case_id: str = Field(..., description="Case identifier in your system")
    items: List[EvidenceItem] = Field(
        ...,
        description="List of evidence items to process",
    )


class TimelineEntry(BaseModel):
    id: str
    case_id: str
    summary: str
    timestamp: Optional[str] = None
    evidence_ids: List[str] = Field(default_factory=list)
    predicted_type: Optional[str] = None
    ocr_used: bool = False


class ProcessEvidenceResponse(BaseModel):
    case_id: str
    timeline: List[TimelineEntry]
    classified_count: int


@router.post("/process", response_model=ProcessEvidenceResponse)
async def process_evidence(payload: ProcessEvidenceRequest):
    """
    v1 stub implementation.

    Later this should:
    - call classifier.py to classify evidence
    - call ocr.py if items reference files
    - call timeline.py to build proper timeline entries

    For now it:
    - validates input
    - logs basic info
    - returns a simple timeline built from the input items
    """
    if not payload.items:
        raise HTTPException(status_code=400, detail="No evidence items provided")

    logger.info(
        f"Processing {len(payload.items)} evidence items for case {payload.case_id}"
    )

    timeline_entries: List[TimelineEntry] = []

    for item in payload.items:
        evidence_id = item.id or str(uuid.uuid4())
        timeline_id = str(uuid.uuid4())

        ocr_text = ""
        if item.media_path:
            ocr_text = safe_extract_text(item.media_path) or ""

        final_text = ocr_text.strip() if ocr_text.strip() else item.content.strip()
        predicted_type = classify_text(final_text)
        timestamp = extract_date(final_text)

        # Simple v1 summary: truncate content
        summary = final_text
        if len(summary) > 140:
            summary = summary[:137] + "..."

        timeline_entries.append(
            TimelineEntry(
                id=timeline_id,
                case_id=payload.case_id,
                summary=summary,
                timestamp=timestamp,
                evidence_ids=[evidence_id],
                predicted_type=predicted_type,
                ocr_used=bool(ocr_text.strip()),
            )
        )

    _persist_timeline_entries(payload.case_id, timeline_entries)

    return ProcessEvidenceResponse(
        case_id=payload.case_id,
        timeline=timeline_entries,
        classified_count=len(payload.items),
    )


@router.post("/ingest", response_model=ProcessEvidenceResponse)
async def ingest_evidence(payload: ProcessEvidenceRequest):
    """
    Ingest evidence items, run OCR + classification + timeline building.

    For v1, this simply forwards to the main process_evidence pipeline so we
    don't duplicate logic. Later we can add extra ingestion-only behavior
    (e.g., storage, hashing, queueing).
    """
    return await process_evidence(payload)
# Note: Additional endpoints for /classify, /ocr would go here in future versions.


@router.get("/timeline/{case_id}", response_model=List[TimelineEntry])
async def get_timeline(case_id: str):
    """
    Return timeline entries for a case_id from MongoDB (or in-memory fallback).
    """
    col = get_collection("timelines")
    if col is None:
        if case_id not in CASE_TIMELINES:
            raise HTTPException(status_code=404, detail="Timeline not found for case_id")
        return CASE_TIMELINES[case_id]

    docs = list(
        col.find({"case_id": case_id}).sort([("timestamp", 1), ("created_at", 1)])
    )
    if not docs:
        raise HTTPException(status_code=404, detail="Timeline not found for case_id")

    entries: List[TimelineEntry] = []
    for d in docs:
        entries.append(
            TimelineEntry(
                id=str(d.get("id") or d.get("_id")),
                case_id=d.get("case_id", case_id),
                summary=d.get("summary", ""),
                timestamp=d.get("timestamp"),
                evidence_ids=d.get("evidence_ids") or [],
                predicted_type=d.get("predicted_type"),
                ocr_used=bool(d.get("ocr_used")),
            )
        )

    return entries

@router.get("/export", summary="Export all evidence as a ZIP file")
async def export_evidence(folder: Optional[str] = None) -> FileResponse:
    """
    Build a ZIP archive from the evidence folder and return it for download.

    Query params:
    - `folder`: optional absolute path to the folder to export. If omitted,
      tries environment variable `EVIDENCE_SOURCE_FOLDER`, then falls back to
      the default `~/Mitchopolis/parenting_evidence/text_logs`.
    """
    # Determine source folder: query param -> env var -> hardcoded default
    if folder:
        evidence_folder = Path(folder).expanduser()
    else:
        env_folder = os.environ.get("EVIDENCE_SOURCE_FOLDER")
        if env_folder:
            evidence_folder = Path(env_folder).expanduser()
        else:
            evidence_folder = Path.home() / "Mitchopolis" / "parenting_evidence" / "text_logs"

    try:
        zip_path = generate_evidence_zip(evidence_folder)
    except FileNotFoundError as e:
        logger.error("Export failed: %s", e)
        raise HTTPException(status_code=404, detail=str(e))
    except Exception:
        logger.exception("Unexpected error while generating export ZIP")
        raise HTTPException(status_code=500, detail="Failed to generate export ZIP")

    return FileResponse(str(zip_path), media_type="application/zip", filename=zip_path.name)
