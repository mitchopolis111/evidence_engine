from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field, field_validator, model_validator

CASE_ID = "BCSC-138865"
SHA256_PATTERN = r"^[a-fA-F0-9]{64}$"


class SourceRef(BaseModel):
    document_id: str = Field(min_length=1)
    sha256: str = Field(pattern=SHA256_PATTERN)
    page: int | None = Field(default=None, ge=1)
    end_page: int | None = Field(default=None, ge=1)
    paragraph: str | None = None
    record_locator: str | None = None
    source_type: str = Field(min_length=1)
    extraction_method: Literal["native", "ocr", "structured", "manual"] = "structured"
    confidence: float | None = Field(default=None, ge=0, le=1)

    @field_validator("sha256")
    @classmethod
    def normalize_sha256(cls, value: str) -> str:
        return value.lower()

    @model_validator(mode="after")
    def validate_page_range(self):
        if self.page is None and self.end_page is not None:
            raise ValueError("end_page requires page")
        if self.page is not None and self.end_page is not None and self.end_page < self.page:
            raise ValueError("end_page must be greater than or equal to page")
        return self


class Person(BaseModel):
    person_id: str = Field(min_length=1)
    case_id: str = CASE_ID
    canonical_name: str = Field(min_length=1)
    role: Literal["claimant", "respondent", "child", "counsel", "other"]
    represents_person_id: str | None = None
    protected_minor: bool = False


class Assertion(BaseModel):
    assertion_id: str = Field(min_length=1)
    case_id: str = CASE_ID
    speaker_person_id: str = Field(min_length=1)
    normalized_claim: str = Field(min_length=1)
    source: SourceRef
    status: Literal["alleged", "disputed", "corroborated", "court_finding", "unknown"] = "unknown"
    human_verified: bool = False
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    contradicting_evidence_ids: list[str] = Field(default_factory=list)


class OFWAttachment(BaseModel):
    filename: str = Field(min_length=1)
    raw_filename: str | None = None
    display_size: str | None = None


class OFWReadReceipt(BaseModel):
    recipient_person_id: str = Field(min_length=1)
    first_viewed_at: AwareDatetime | None = None
    first_viewed_at_raw: str | None = None


class OFWMessage(BaseModel):
    message_id: str = Field(min_length=1)
    case_id: str = CASE_ID
    sender_person_id: str = Field(min_length=1)
    recipient_person_ids: list[str] = Field(min_length=1)
    sent_at: AwareDatetime
    sent_at_raw: str | None = None
    source_timezone: str | None = None
    read_at: AwareDatetime | None = None
    read_receipts: list[OFWReadReceipt] = Field(default_factory=list)
    subject: str | None = None
    body: str
    attachments: list[OFWAttachment] = Field(default_factory=list)
    report_message_number: int | None = Field(default=None, ge=1)
    report_message_total: int | None = Field(default=None, ge=1)
    content_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    source: SourceRef

    @field_validator("recipient_person_ids")
    @classmethod
    def validate_recipients(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("recipient_person_ids must be unique")
        return value

    @field_validator("content_sha256")
    @classmethod
    def normalize_content_sha256(cls, value: str | None) -> str | None:
        return value.lower() if value else value

    @model_validator(mode="after")
    def validate_receipts(self):
        if self.read_at is not None and self.read_at < self.sent_at:
            raise ValueError("read_at cannot be before sent_at")
        recipient_ids = set(self.recipient_person_ids)
        receipt_ids = [receipt.recipient_person_id for receipt in self.read_receipts]
        if len(receipt_ids) != len(set(receipt_ids)):
            raise ValueError("read receipts must reference unique recipients")
        for receipt in self.read_receipts:
            if receipt.recipient_person_id not in recipient_ids:
                raise ValueError("read receipt must reference a recipient")
            if receipt.first_viewed_at is not None and receipt.first_viewed_at < self.sent_at:
                raise ValueError("first_viewed_at cannot be before sent_at")
        if self.report_message_number is not None and self.report_message_total is not None:
            if self.report_message_number > self.report_message_total:
                raise ValueError("report_message_number cannot exceed report_message_total")
        return self


class OFWCallEvent(BaseModel):
    event_id: str = Field(min_length=1)
    case_id: str = CASE_ID
    caller_person_id: str = Field(min_length=1)
    related_child_person_id: str | None = None
    scheduled_at: AwareDatetime | None = None
    attempted_at: AwareDatetime
    status: Literal["attempted", "completed", "unavailable", "missed", "unknown"]
    source: SourceRef


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


CASE_PEOPLE = [
    Person(person_id="person_lindsay_alene_mcclean", canonical_name="Lindsay Alene McClean", role="claimant"),
    Person(person_id="person_mitchel_watson", canonical_name="Mitchel Watson", role="respondent"),
    Person(person_id="person_sofia_rae_watson", canonical_name="Sofia Rae Watson", role="child", protected_minor=True),
    Person(person_id="person_laura_watson", canonical_name="Laura Watson", role="other"),
    Person(
        person_id="person_clayton_miller",
        canonical_name="Clayton Miller",
        role="counsel",
        represents_person_id="person_lindsay_alene_mcclean",
    ),
]

PERSON_ID_BY_DISPLAY_NAME = {
    "lindsay alene mcclean": "person_lindsay_alene_mcclean",
    "lindsay mcclean": "person_lindsay_alene_mcclean",
    "mitchel watson": "person_mitchel_watson",
    "mitch watson": "person_mitchel_watson",
    "sofia rae watson": "person_sofia_rae_watson",
    "sofia watson": "person_sofia_rae_watson",
    "laura watson": "person_laura_watson",
    "clayton miller": "person_clayton_miller",
}
