from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from typing import Any, Dict, Optional
import time
import uvicorn

from .router import router as evidence_router

APP_VERSION = "1.0.0"

app = FastAPI(
    title="Evidence Engine API",
    version=APP_VERSION,
    description="OCR ingestion and structured document extraction service."
)
app.include_router(evidence_router, prefix="/api/evidence", tags=["evidence"])

# -------------------------
# Schemas
# -------------------------

class UploadResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "filename": "sample.pdf",
                "text": "Mock OCR text extraction result.",
                "confidence": 0.94,
                "structured": {"entities": [], "dates": [], "keywords": []},
                "processing_ms": 842,
            }
        }
    )

    success: bool
    filename: str
    text: str = Field(..., description="Raw OCR extracted text")
    confidence: float
    structured: Dict[str, Any] = Field(..., description="Structured extracted data")
    processing_ms: float


class ErrorResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": False,
                "error": "Invalid file type",
            }
        }
    )

    success: bool
    error: str


# -------------------------
# Utility Functions
# -------------------------

ALLOWED_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png"
}


def mock_ocr_process(file_bytes: bytes) -> dict:
    """
    Replace this with real OCR pipeline.
    """
    extracted_text = "Mock OCR text extraction result."
    structured_output = {
        "entities": [],
        "dates": [],
        "keywords": []
    }
    confidence_score = 0.94

    return {
        "text": extracted_text,
        "structured": structured_output,
        "confidence": confidence_score
    }


# -------------------------
# Endpoints
# -------------------------

@app.get("/health")
def get_health():
    return {"status": "ok"}


@app.get("/version")
def get_version():
    return {"version": APP_VERSION}


@app.post(
    "/upload",
    response_model=UploadResponse,
    responses={
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def upload_document(
    file: UploadFile = File(...),
    metadata: Optional[str] = Form(None)
):
    start_time = time.perf_counter()

    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Invalid file type"
        )

    try:
        file_bytes = await file.read()

        if not file_bytes:
            raise HTTPException(
                status_code=400,
                detail="Empty file"
            )

        # ---- OCR Processing ----
        result = mock_ocr_process(file_bytes)

        processing_ms = (time.perf_counter() - start_time) * 1000

        return UploadResponse(
            success=True,
            filename=file.filename,
            text=result["text"],
            confidence=result["confidence"],
            structured=result["structured"],
            processing_ms=round(processing_ms, 2),
        )

    except HTTPException as e:
        return JSONResponse(
            status_code=e.status_code,
            content={
                "success": False,
                "error": e.detail
            },
        )

    except Exception:
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": "Processing error"
            },
        )


if __name__ == "__main__":
    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
