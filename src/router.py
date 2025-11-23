from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional
import uuid
import logging
from .classifier import classify_text
from .ocr import safe_extract_text
from .ocr import safe_extract_text

router = APIRouter()

logger = logging.getLogger(__name__)


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

        # Simple v1 summary: truncate content
        summary = final_text
        if len(summary) > 140:
            summary = summary[:137] + "..."

        timeline_entries.append(
            TimelineEntry(
                id=timeline_id,
                case_id=payload.case_id,
                summary=summary,
                timestamp=None,          # TODO: derive when we have real dates
                evidence_ids=[evidence_id],
                predicted_type=predicted_type,
                ocr_used=bool(ocr_text.strip()),
            )
        )

    return ProcessEvidenceResponse(
        case_id=payload.case_id,

        timeline=timeline_entries,
        classified_count=len(payload.items),
    )
# Note: Additional endpoints for /classify, /ocr, /timeline would go here in future versions.
