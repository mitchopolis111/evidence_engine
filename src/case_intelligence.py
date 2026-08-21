from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

CASE_ID = "BCSC-138865"


class SourceRef(BaseModel):
    document_id: str
    sha256: str = Field(pattern=r"^[a-fA-F0-9]{64}$")
    page: int | None = Field(default=None, ge=1)
    paragraph: str | None = None
    source_type: str
    extraction_method: Literal["native", "ocr", "structured", "manual"] = "structured"
    confidence: float | None = Field(default=None, ge=0, le=1)


class Person(BaseModel):
    person_id: str
    case_id: str = CASE_ID
    canonical_name: str
    role: Literal["claimant", "respondent", "child", "counsel", "other"]
    represents_person_id: str | None = None
    protected_minor: bool = False


class Assertion(BaseModel):
    assertion_id: str
    case_id: str = CASE_ID
    speaker_person_id: str
    normalized_claim: str
    source: SourceRef
    status: Literal["alleged", "disputed", "corroborated", "court_finding", "unknown"] = "unknown"
    human_verified: bool = False
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    contradicting_evidence_ids: list[str] = Field(default_factory=list)


class OFWMessage(BaseModel):
    message_id: str
    case_id: str = CASE_ID
    sender_person_id: str
    recipient_person_ids: list[str]
    sent_at: datetime
    read_at: datetime | None = None
    body: str
    source: SourceRef


class OFWCallEvent(BaseModel):
    event_id: str
    case_id: str = CASE_ID
    caller_person_id: str
    related_child_person_id: str | None = None
    scheduled_at: datetime | None = None
    attempted_at: datetime
    status: Literal["attempted", "completed", "unavailable", "missed", "unknown"]
    source: SourceRef


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


CASE_PEOPLE = [
    Person(person_id="person_lindsay_alene_mcclean", canonical_name="Lindsay Alene McClean", role="claimant"),
    Person(person_id="person_mitchel_watson", canonical_name="Mitchel Watson", role="respondent"),
    Person(person_id="person_sofia_rae_watson", canonical_name="Sofia Rae Watson", role="child", protected_minor=True),
    Person(
        person_id="person_clayton_miller",
        canonical_name="Clayton Miller",
        role="counsel",
        represents_person_id="person_lindsay_alene_mcclean",
    ),
]
