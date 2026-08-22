from pathlib import Path
import os
from fastapi.responses import FileResponse
from .utils.zip_exporter import UnsafeExportPathError, generate_evidence_zip
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from typing import Any, Dict, List, Optional
import uuid
import logging
from .classifier import classify_text
from .ocr import extract_text_with_diagnostics
from .timeline import extract_date
from .db import get_collection
from datetime import datetime
import hashlib
try:
    from pymongo import UpdateOne
except ImportError:
    UpdateOne = None

router = APIRouter()

logger = logging.getLogger(__name__)

DEFAULT_EVIDENCE_ROOT = Path(__file__).resolve().parents[2] / "parenting_evidence"
DEFAULT_EXPORT_SOURCE = DEFAULT_EVIDENCE_ROOT / "text_logs"

# In-memory timeline cache keyed by case_id (dev-only fallback).
CASE_TIMELINES: dict[str, List["TimelineEntry"]] = {}


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _configured_export_root(raw_path: str, variable_name: str) -> Path:
    root = Path(raw_path).expanduser()
    if not root.is_absolute():
        logger.error("%s must contain an absolute path", variable_name)
        raise HTTPException(
            status_code=500,
            detail="Export path configuration is invalid",
        )

    resolved_root = root.resolve(strict=False)
    if resolved_root == Path(resolved_root.anchor):
        logger.error("%s must not authorize the filesystem root", variable_name)
        raise HTTPException(
            status_code=500,
            detail="Export path configuration is invalid",
        )
    return resolved_root


def _approved_export_roots() -> List[Path]:
    roots = [DEFAULT_EVIDENCE_ROOT.resolve(strict=False)]

    source_folder = os.environ.get("EVIDENCE_SOURCE_FOLDER")
    if source_folder:
        roots.append(
            _configured_export_root(source_folder, "EVIDENCE_SOURCE_FOLDER")
        )

    extra_roots = os.environ.get("EVIDENCE_EXPORT_ALLOWED_ROOTS", "")
    for raw_root in extra_roots.split(os.pathsep):
        if raw_root.strip():
            roots.append(
                _configured_export_root(
                    raw_root.strip(), "EVIDENCE_EXPORT_ALLOWED_ROOTS"
                )
            )

    return list(dict.fromkeys(roots))


def _resolve_export_folder(folder: Optional[str]) -> Path:
    configured_source = os.environ.get("EVIDENCE_SOURCE_FOLDER")
    raw_folder = folder or configured_source or str(DEFAULT_EXPORT_SOURCE)
    candidate = Path(raw_folder).expanduser()

    if not candidate.is_absolute():
        if folder:
            raise HTTPException(
                status_code=400,
                detail="Export folder must be an absolute path",
            )
        logger.error("EVIDENCE_SOURCE_FOLDER must contain an absolute path")
        raise HTTPException(
            status_code=500,
            detail="Export path configuration is invalid",
        )

    try:
        resolved_folder = candidate.resolve(strict=False)
    except (OSError, RuntimeError, ValueError):
        raise HTTPException(status_code=400, detail="Export folder path is invalid")

    if not any(
        _is_within(resolved_folder, approved_root)
        for approved_root in _approved_export_roots()
    ):
        raise HTTPException(
            status_code=403,
            detail="Export folder is outside the approved evidence roots",
        )
    if not resolved_folder.exists():
        raise HTTPException(status_code=404, detail="Export folder not found")
    if not resolved_folder.is_dir():
        raise HTTPException(
            status_code=400,
            detail="Export source must be a directory",
        )

    return resolved_folder


def _persist_timeline_entries(case_id: str, entries: List["TimelineEntry"]):
    """
    Persist timeline entries to MongoDB if configured. Falls back to memory when
    Mongo is not available.
    """
    col = get_collection("timelines")
    if col is None or UpdateOne is None:
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
            "extraction_method": entry.extraction_method,
            "processing_warnings": [
                warning.model_dump() for warning in entry.processing_warnings
            ],
            "evidence_hash": entry.evidence_hash,
            "source_metadata": entry.source_metadata,
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
    except Exception as exc:
        logger.warning(
            "Failed to persist timeline entries to MongoDB; using in-memory fallback: %s",
            type(exc).__name__,
        )
        CASE_TIMELINES[case_id] = entries


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
    source_metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Structured provenance for the source record, if available",
    )


class ProcessEvidenceRequest(BaseModel):
    case_id: str = Field(..., description="Case identifier in your system")
    items: List[EvidenceItem] = Field(
        ...,
        description="List of evidence items to process",
    )


class ProcessingWarning(BaseModel):
    code: str
    message: str


class TimelineEntry(BaseModel):
    id: str
    case_id: str
    summary: str
    timestamp: Optional[str] = None
    evidence_ids: List[str] = Field(default_factory=list)
    predicted_type: Optional[str] = None
    ocr_used: bool = False
    extraction_method: str = "provided_content"
    processing_warnings: List[ProcessingWarning] = Field(default_factory=list)
    evidence_hash: Optional[str] = None
    source_metadata: Optional[Dict[str, Any]] = None


class ProcessEvidenceResponse(BaseModel):
    case_id: str
    timeline: List[TimelineEntry]
    classified_count: int


class GmailAttachmentRecord(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    message_id: str = Field(..., description="Gmail message id containing the attachment")
    thread_id: Optional[str] = Field(
        default=None,
        description="Gmail conversation thread id, when available",
    )
    thread_subject: Optional[str] = Field(
        default=None,
        description="Normalized Gmail conversation subject or thread key",
    )
    attachment_id: Optional[str] = Field(
        default=None,
        description="Gmail attachment id, when available",
    )
    filename: str = Field(..., description="Attachment filename")
    media_path: Optional[str] = Field(
        default=None,
        description="Local path to the downloaded attachment",
    )
    mime_type: Optional[str] = None
    size_bytes: Optional[int] = None
    content: Optional[str] = Field(
        default=None,
        description="Optional extracted or descriptive text for the attachment",
    )
    email_ts: Optional[str] = Field(
        default=None,
        description="Timestamp from the source email",
    )
    from_: Optional[str] = Field(default=None, alias="from")
    to: List[str] = Field(default_factory=list)
    cc: List[str] = Field(default_factory=list)
    subject: Optional[str] = None
    snippet: Optional[str] = None
    display_url: Optional[str] = None
    labels: List[str] = Field(default_factory=list)
    source_label: Optional[str] = Field(
        default=None,
        description="Human-readable Gmail label that produced this record",
    )
    law_firm: Optional[str] = Field(
        default=None,
        description="Law office associated with the Gmail label or sender",
    )


class GmailIntakeRequest(BaseModel):
    case_id: str = Field(..., description="Case identifier in your system")
    attachments: List[GmailAttachmentRecord] = Field(
        ...,
        description="Gmail attachments downloaded to local storage",
    )
    tags: List[str] = Field(default_factory=list)


def _hash_file(path: str) -> Optional[str]:
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()
    except (FileNotFoundError, PermissionError, OSError):
        return None


def _stable_timeline_id(case_id: str, evidence_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{case_id}:{evidence_id}"))


@router.post("/process", response_model=ProcessEvidenceResponse)
async def process_evidence(payload: ProcessEvidenceRequest):
    """
    Process evidence into source-linked timeline entries with extraction
    diagnostics. Media extraction remains best-effort; supplied content is used
    as a fallback and the reason is exposed in processing_warnings.
    """
    if not payload.items:
        raise HTTPException(status_code=400, detail="No evidence items provided")

    logger.info(
        f"Processing {len(payload.items)} evidence items for case {payload.case_id}"
    )

    timeline_entries: List[TimelineEntry] = []

    for item in payload.items:
        evidence_hash = None
        if item.media_path:
            evidence_hash = _hash_file(item.media_path)

        if item.id:
            evidence_id = item.id
        elif evidence_hash:
            evidence_id = f"sha256:{evidence_hash}"
        else:
            evidence_id = str(uuid.uuid4())

        timeline_id = _stable_timeline_id(payload.case_id, evidence_id)

        media_text = ""
        processing_warnings: List[ProcessingWarning] = []
        extraction_method = "provided_content"
        if item.media_path:
            extraction = extract_text_with_diagnostics(item.media_path)
            media_text = extraction.text
            processing_warnings = [
                ProcessingWarning(code=warning.code, message=warning.message)
                for warning in extraction.warnings
            ]

        supplied_content = item.content.strip()
        if media_text:
            final_text = media_text
            extraction_method = extraction.method
        elif supplied_content:
            final_text = supplied_content
            if item.media_path:
                extraction_method = "provided_content_fallback"
        else:
            final_text = ""
            extraction_method = "none"
            processing_warnings.append(
                ProcessingWarning(
                    code="no_usable_text",
                    message="Neither media extraction nor supplied content produced usable text.",
                )
            )

        if processing_warnings:
            log_warning = (
                logger.warning
                if any(
                    warning.code != "ocr_review_required"
                    for warning in processing_warnings
                )
                else logger.info
            )
            log_warning(
                "Evidence item %s processing warnings: %s",
                evidence_id,
                ",".join(warning.code for warning in processing_warnings),
            )

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
                ocr_used=bool(media_text),
                extraction_method=extraction_method,
                processing_warnings=processing_warnings,
                evidence_hash=evidence_hash,
                source_metadata=item.source_metadata,
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


@router.post("/gmail/intake", response_model=ProcessEvidenceResponse)
async def ingest_gmail_attachments(payload: GmailIntakeRequest):
    """
    Import downloaded Gmail attachments through the same processing path used by
    manual uploads and folder watchers while preserving email provenance.
    """
    if not payload.attachments:
        raise HTTPException(status_code=400, detail="No Gmail attachments provided")

    base_tags = [tag for tag in payload.tags if tag]
    for required_tag in ("gmail",):
        if required_tag not in base_tags:
            base_tags.append(required_tag)

    items: List[EvidenceItem] = []
    for attachment in payload.attachments:
        tags = list(base_tags)
        for optional_tag in (attachment.law_firm, attachment.source_label):
            if optional_tag and optional_tag not in tags:
                tags.append(optional_tag)

        source_metadata = {
            "source": "gmail",
            "thread_id": attachment.thread_id,
            "thread_subject": attachment.thread_subject,
            "message_id": attachment.message_id,
            "email_ts": attachment.email_ts,
            "from": attachment.from_,
            "to": attachment.to,
            "cc": attachment.cc,
            "subject": attachment.subject,
            "snippet": attachment.snippet,
            "display_url": attachment.display_url,
            "labels": attachment.labels,
            "source_label": attachment.source_label,
            "law_firm": attachment.law_firm,
            "attachment": {
                "attachment_id": attachment.attachment_id,
                "filename": attachment.filename,
                "mime_type": attachment.mime_type,
                "size_bytes": attachment.size_bytes,
            },
        }
        evidence_id = str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                ":".join(
                [
                    payload.case_id,
                    attachment.thread_id or "",
                    attachment.thread_subject or "",
                    attachment.message_id,
                    attachment.attachment_id or attachment.filename,
                ]
            ),
            )
        )
        items.append(
            EvidenceItem(
                id=evidence_id,
                source="gmail",
                content=attachment.content or f"Gmail attachment: {attachment.filename}",
                media_path=attachment.media_path,
                tags=tags,
                source_metadata=source_metadata,
            )
        )

    return await process_evidence(
        ProcessEvidenceRequest(case_id=payload.case_id, items=items)
    )
# Note: Additional endpoints for /classify, /ocr would go here in future versions.


@router.get("/timeline/{case_id}", response_model=List[TimelineEntry])
async def get_timeline(case_id: str):
    """
    Return timeline entries for a case_id from MongoDB (or in-memory fallback).
    """
    col = get_collection("timelines")
    if col is not None:
        try:
            docs = list(
                col.find({"case_id": case_id}).sort(
                    [("timestamp", 1), ("created_at", 1)]
                )
            )
        except Exception as exc:
            logger.warning(
                "Failed to read timeline entries from MongoDB; using in-memory fallback: %s",
                type(exc).__name__,
            )
        else:
            if docs:
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
                            extraction_method=d.get(
                                "extraction_method", "provided_content"
                            ),
                            processing_warnings=d.get("processing_warnings") or [],
                            evidence_hash=d.get("evidence_hash"),
                            source_metadata=d.get("source_metadata"),
                        )
                    )

                return entries

    if case_id not in CASE_TIMELINES:
        raise HTTPException(status_code=404, detail="Timeline not found for case_id")

    return CASE_TIMELINES[case_id]

@router.get("/export", summary="Export all evidence as a ZIP file")
async def export_evidence(folder: Optional[str] = None) -> FileResponse:
    """
    Build a ZIP archive from the evidence folder and return it for download.

    Query params:
    - `folder`: optional absolute path under an approved evidence root. If
      omitted, tries environment variable `EVIDENCE_SOURCE_FOLDER`, then falls
      back to `parenting_evidence/text_logs` under the Mitchopolis workspace.
    """
    evidence_folder = _resolve_export_folder(folder)

    try:
        zip_path = generate_evidence_zip(evidence_folder)
    except FileNotFoundError:
        logger.warning("Export source disappeared before packaging")
        raise HTTPException(status_code=404, detail="Export folder not found")
    except NotADirectoryError:
        raise HTTPException(status_code=400, detail="Export source must be a directory")
    except UnsafeExportPathError as exc:
        logger.warning("Rejected unsafe export source: %s", exc)
        raise HTTPException(
            status_code=400,
            detail="Export source contains unsafe filesystem entries",
        )
    except Exception:
        logger.exception("Unexpected error while generating export ZIP")
        raise HTTPException(status_code=500, detail="Failed to generate export ZIP")

    return FileResponse(str(zip_path), media_type="application/zip", filename=zip_path.name)
